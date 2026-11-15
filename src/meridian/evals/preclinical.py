"""Evaluation of preclinical.tox_study_monitor (docs/preclinical-eval.md, pre-registered).

Null cuts: the real study with the group labels of its animals permuted within sex and
phase (seeds 1 to 20). Planted sets: a null cut with liver hypertrophy reset, then ALT and
AST, body weight gain, liver weight, hypertrophy incidence and a single-animal outlier
planted (dev seeds 101 to 110, holdout 201 to 210), each with its ground truth
(meridian.faults.inject.GroundTruth). The agent runs in process on each copy through its
own run(); nothing is written to the ledger, so no evaluation finding reaches a reviewer.
"""

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import polars as pl

from meridian.data.send import SEND_AREA
from meridian.domain.enums import FindingKind
from meridian.faults.catalog import FaultRecord
from meridian.faults.inject import GroundTruth
from meridian.ledger.hashing import canonical_json
from meridian.platform.agent_settings import ToxStudyMonitorConfig
from meridian.preclinical.analysis import (
    DATA_QUALITY,
    MAIN,
    Summary,
    analyse,
    by_key,
    read_design,
)

NULL_SEEDS = tuple(range(1, 21))
SET_SEEDS = {"dev": tuple(range(101, 111)), "holdout": tuple(range(201, 211))}
LB_FACTORS: dict[str, float] = {"mid": 1.5, "high": 2.5}
GAIN_FACTOR_HIGH = 0.7
LIVER_FACTORS: dict[str, float] = {"mid": 1.10, "high": 1.25}
HYPERTROPHY_COUNTS: dict[str, int] = {"mid": 3, "high": 8}
OUTLIER_MULTIPLE = 5.0
PLANT: dict[str, object] = {
    "lb_factors": LB_FACTORS,
    "gain_factor_high": GAIN_FACTOR_HIGH,
    "liver_factors": LIVER_FACTORS,
    "hypertrophy_counts": HYPERTROPHY_COUNTS,
    "outlier_multiple": OUTLIER_MULTIPLE,
}
SCENARIO = "docs/preclinical-eval.md#planted-effects"
CHANGE = "change"  # dose_related_change or pairwise_change
INCIDENCE = "incidence"  # dose_related_incidence or pairwise_incidence
ALLOWED = "allowed"  # a consequence of a planted effect: not required, not a false positive


def load_study(send_cut_dir: Path) -> dict[str, pl.DataFrame]:
    return {
        p.stem: pl.read_parquet(p) for p in sorted((send_cut_dir / SEND_AREA).glob("*.parquet"))
    }


def permute(tables: Mapping[str, pl.DataFrame], seed: int) -> dict[str, pl.DataFrame]:
    """The group labels (SETCD, ARMCD, ARM) of DM permuted among the analysed animals of
    each sex and phase; toxicokinetic animals keep theirs. Nothing else changes."""
    rng = np.random.default_rng(seed)
    dm = tables["dm"]
    design = read_design(dm, tables["tx"], tables.get("ds"))
    animals = design.animals.sort("USUBJID")
    new: dict[str, int] = {}
    labels = dm.select("USUBJID", "SETCD", "ARMCD", "ARM")
    for phase in (MAIN, "recovery"):
        for sex in ("M", "F"):
            ids = animals.filter((pl.col("phase") == phase) & (pl.col("SEX") == sex))[
                "USUBJID"
            ].to_list()
            order = rng.permutation(len(ids))
            for target, source in zip(ids, [ids[i] for i in order], strict=True):
                new[target] = labels["USUBJID"].to_list().index(source)
    rows = labels.rows()
    out = []
    for i, uid in enumerate(dm["USUBJID"].to_list()):
        j = new.get(uid, i)
        out.append(rows[j][1:])
    swapped = pl.DataFrame(out, schema=["SETCD", "ARMCD", "ARM"], orient="row")
    return {**tables, "dm": dm.with_columns(swapped)}


def _ids(tables: Mapping[str, pl.DataFrame], sex: str, rank: int, phase: str = MAIN) -> list[str]:
    design = read_design(tables["dm"], tables["tx"], tables.get("ds"))
    a = design.animals.filter(
        (pl.col("SEX") == sex) & (pl.col("rank") == rank) & (pl.col("phase") == phase)
    )
    return sorted(a["USUBJID"].to_list())


@dataclass
class Planted:
    tables: dict[str, pl.DataFrame]
    faults: list[FaultRecord] = field(default_factory=list)


def plant(tables: Mapping[str, pl.DataFrame], seed: int) -> Planted:
    """The pre-registered effects on a copy (main phase, both sexes)."""
    rng = np.random.default_rng(seed)
    t = dict(tables)
    faults: list[FaultRecord] = []
    # Reset liver hypertrophy everywhere, so the planted incidence is the only one.
    mi = t["mi"]
    hyper = (pl.col("MISPEC") == "LIVER") & (pl.col("MISTRESC") == "HYPERTROPHY")
    t["mi"] = mi.with_columns(
        pl.when(hyper).then(pl.lit("NORMAL")).otherwise(pl.col("MISTRESC")).alias("MISTRESC"),
        pl.when(hyper).then(pl.lit("")).otherwise(pl.col("MISEV")).alias("MISEV"),
    )
    n = 0
    for sex in ("M", "F"):
        mid, high = _ids(t, sex, 2), _ids(t, sex, 3)
        for test in ("ALT", "AST"):
            touched = 0
            for ids, f in ((mid, LB_FACTORS["mid"]), (high, LB_FACTORS["high"])):
                target = (pl.col("LBTESTCD") == test) & pl.col("USUBJID").is_in(ids)
                touched += t["lb"].filter(target).height
                t["lb"] = t["lb"].with_columns(
                    pl.when(target).then(pl.col("LBSTRESN") * f).otherwise(pl.col("LBSTRESN"))
                )
            n += 1
            faults.append(
                _fault(
                    n,
                    "lb_increase",
                    f"lb:{test}:{sex}:main",
                    LB_FACTORS,
                    CHANGE,
                    {"lb": touched},
                )
            )
        # Body weight gain: the final-day weight of each high-dose animal lowered so that its
        # gain falls by 30%.
        bw = t["bw"]
        rows = bw.filter((pl.col("BWTESTCD") == "BW") & pl.col("USUBJID").is_in(high))
        touched = 0
        for uid in high:
            mine = rows.filter(pl.col("USUBJID") == uid).sort("BWDY")
            if mine.height < 2:
                continue
            first, last_day = mine["BWSTRESN"][0], mine["BWDY"].max()
            target = (
                (pl.col("USUBJID") == uid)
                & (pl.col("BWTESTCD") == "BW")
                & (pl.col("BWDY") == last_day)
            )
            g = GAIN_FACTOR_HIGH
            bw = bw.with_columns(
                pl.when(target)
                .then(first + (pl.col("BWSTRESN") - first) * g)
                .otherwise(pl.col("BWSTRESN"))
                .alias("BWSTRESN")
            )
            touched += 1
        t["bw"] = bw
        n += 1
        faults.append(
            _fault(
                n,
                "bw_gain_decrease",
                f"bw:GAIN:{sex}:main",
                {"high": GAIN_FACTOR_HIGH},
                CHANGE,
                {"bw": touched},
            )
        )
        n += 1
        faults.append(_fault(n, "consequence", f"bw:BW:{sex}:main", {}, ALLOWED, {}))
        # Liver weight.
        touched = 0
        for ids, f in (
            (mid, LIVER_FACTORS["mid"]),
            (high, LIVER_FACTORS["high"]),
        ):
            target = (pl.col("OMSPEC") == "LIVER") & pl.col("USUBJID").is_in(ids)
            touched += t["om"].filter(target).height
            t["om"] = t["om"].with_columns(
                pl.when(target).then(pl.col("OMSTRESN") * f).otherwise(pl.col("OMSTRESN"))
            )
        n += 1
        faults.append(
            _fault(
                n,
                "organ_weight_increase",
                f"om:LIVER:abs:{sex}:main",
                LIVER_FACTORS,
                CHANGE,
                {"om": touched},
            )
        )
        n += 1
        faults.append(_fault(n, "consequence", f"om:LIVER:rel:{sex}:main", {}, ALLOWED, {}))
        # Hepatocellular hypertrophy in 3 mid-dose and 8 high-dose animals examined.
        examined = set(t["mi"].filter(pl.col("MISPEC") == "LIVER")["USUBJID"].to_list())
        added = []
        for ids, k in (
            (mid, HYPERTROPHY_COUNTS["mid"]),
            (high, HYPERTROPHY_COUNTS["high"]),
        ):
            pool = sorted(i for i in ids if i in examined)
            chosen = sorted(rng.choice(pool, size=min(k, len(pool)), replace=False).tolist())
            for uid in chosen:
                added.append(
                    {
                        "USUBJID": uid,
                        "MISPEC": "LIVER",
                        "MISTRESC": "HYPERTROPHY",
                        "MISEV": str(rng.choice(["MINIMAL", "MILD"])),
                    }
                )
        extra = pl.DataFrame(added).with_columns(
            pl.lit(t["mi"]["STUDYID"][0]).alias("STUDYID"),
            pl.lit("MI").alias("DOMAIN"),
            pl.lit(9000.0).alias("MISEQ"),
            pl.lit("").alias("MISTAT"),
        )
        t["mi"] = pl.concat([t["mi"], extra], how="diagonal_relaxed")
        n += 1
        faults.append(
            _fault(
                n,
                "incidence_increase",
                f"mi:LIVER:HYPERTROPHY:{sex}:main",
                {"mid": 3.0, "high": 8.0},
                INCIDENCE,
                {"mi": len(added)},
            )
        )
    # One high-dose male's creatinine at five times its group's median: must not be raised.
    high_m = _ids(t, "M", 3)
    creat = t["lb"].filter((pl.col("LBTESTCD") == "CREAT") & pl.col("USUBJID").is_in(high_m))
    if creat.height:
        median = float(creat["LBSTRESN"].cast(pl.Float64).median() or 0.0)  # type: ignore[arg-type]
        uid = sorted(creat["USUBJID"].unique().to_list())[
            int(rng.integers(creat["USUBJID"].n_unique()))
        ]
        target = (pl.col("LBTESTCD") == "CREAT") & (pl.col("USUBJID") == uid)
        t["lb"] = t["lb"].with_columns(
            pl.when(target)
            .then(pl.lit(median * OUTLIER_MULTIPLE))
            .otherwise(pl.col("LBSTRESN"))
            .alias("LBSTRESN")
        )
        n += 1
        faults.append(
            _fault(
                n,
                "outlier_single_animal",
                "lb:CREAT:M:main",
                {"multiple": OUTLIER_MULTIPLE},
                None,
                {"lb": 1},
            )
        )
    return Planted(t, faults)


def _fault(
    n: int,
    kind: str,
    target: str,
    params: Mapping[str, float],
    check: str | None,
    rows: Mapping[str, int],
) -> FaultRecord:
    return FaultRecord(
        fault_id=f"F{n:02d}",
        fault_type=kind,
        target=target,
        params=dict(params),
        expected_kind=FindingKind.TOX_SIGNAL,
        kri=check,
        rows_touched=dict(rows),
        achieved={},
    )


# The agent, run on one copy: (tables, cut id) to the checks of its drafts. Given by the
# caller (meridian.preclinical.inprocess.run_checks), so this module imports no agent code.
RunFn = Callable[[Mapping[str, pl.DataFrame], str], list[str]]


def target_of(check: str) -> str:
    return check.split(":", 1)[1]


def is_effect(check: str) -> bool:
    return not check.startswith(DATA_QUALITY)


def copy_id(kind: str, seed: int) -> str:
    return "PRE-" + hashlib.sha256(f"{kind}:{seed}".encode()).hexdigest()[:8].upper()


@dataclass(frozen=True, slots=True)
class CopyResult:
    label: str
    cut_id: str
    effect_findings: tuple[str, ...]
    data_quality: tuple[str, ...]
    found: tuple[str, ...] = ()  # fault ids found
    missed: tuple[str, ...] = ()
    false_positives: tuple[str, ...] = ()
    outlier_raised: bool = False
    both_doses_flagged: tuple[str, ...] = ()  # ALT/AST targets with mid and high flagged


def evaluate_null(base: Mapping[str, pl.DataFrame], run: RunFn) -> list[CopyResult]:
    out = []
    for seed in NULL_SEEDS:
        cut = copy_id("null", seed)
        checks = sorted(run(permute(base, seed), cut))
        out.append(
            CopyResult(
                f"null_{seed:02d}",
                cut,
                tuple(c for c in checks if is_effect(c)),
                tuple(c for c in checks if not is_effect(c)),
            )
        )
    return out


def evaluate_set(
    name: str,
    base: Mapping[str, pl.DataFrame],
    cfg: ToxStudyMonitorConfig,
    run: RunFn,
    base_manifest_sha256: str,
    ground_truth_dir: Path | None = None,
) -> list[CopyResult]:
    out = []
    for i, seed in enumerate(SET_SEEDS[name], start=1):
        cut = copy_id(name, seed)
        planted = plant(permute(base, seed), seed)
        checks = sorted(run(planted.tables, cut))
        analysis = by_key(analyse(planted.tables, cfg))
        effects = [c for c in checks if is_effect(c)]
        found: list[str] = []
        missed: list[str] = []
        both: list[str] = []
        faults = []
        for f in planted.faults:
            hits = [c for c in effects if target_of(c) == f.target]
            s = analysis.get(f.target)
            achieved: dict[str, float] = {}
            if s is not None:
                for g in s.groups[1:]:
                    if g.pct is not None:
                        achieved[f"pct_rank{g.rank}"] = round(g.pct, 2)
                    achieved[f"p_rank{g.rank}"] = round(g.p, 6) if g.p is not None else -1.0
            faults.append(f.model_copy(update={"achieved": achieved}))
            if f.kri in (CHANGE, INCIDENCE):
                want_down = f.fault_type == "bw_gain_decrease"
                ok = [
                    c
                    for c in hits
                    if c.startswith(("dose_related_" + f.kri, "pairwise_" + f.kri))
                    and s is not None
                    and _direction_ok(s, down=want_down)
                ]
                (found if ok else missed).append(f.fault_id)
                if (
                    f.fault_type == "lb_increase"
                    and s is not None
                    and {2, 3} <= {g.rank for g in s.groups if g.flagged}
                ):
                    both.append(f.target)
        allowed = {f.target for f in planted.faults}
        fps = [c for c in effects if target_of(c) not in allowed]
        outlier = any(target_of(c) == "lb:CREAT:M:main" for c in effects)
        if ground_truth_dir is not None:
            _write_truth(ground_truth_dir, name, i, seed, cut, base_manifest_sha256, faults)
        out.append(
            CopyResult(
                f"preclinical_{name}_{i:02d}",
                cut,
                tuple(effects),
                tuple(c for c in checks if not is_effect(c)),
                tuple(found),
                tuple(missed),
                tuple(fps),
                outlier,
                tuple(both),
            )
        )
    return out


def _direction_ok(s: Summary, *, down: bool) -> bool:
    flagged = [g for g in s.groups if g.flagged]
    if not flagged:
        return False
    if s.endpoint.kind == "incidence":
        return True
    return all(((g.pct or 0) < 0) == down for g in flagged)


def _write_truth(
    root: Path, name: str, i: int, seed: int, cut: str, base_sha: str, faults: Sequence[FaultRecord]
) -> None:
    scenario = canonical_json(PLANT)
    truth = GroundTruth(
        cut_id=cut,
        scenario_path=SCENARIO,
        scenario_sha256=hashlib.sha256(scenario.encode()).hexdigest(),
        seed=seed,
        base_cut="TOX-FINAL",
        base_manifest_sha256=base_sha,
        faults=tuple(faults),
        label=f"preclinical_{name}_{i:02d}",
    )
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{cut}.json"
    text = truth.dumps()
    if path.exists() and path.read_text() != text:
        raise ValueError(f"{path} exists with other content; ground truth is never rewritten")
    path.write_text(text)


def summarise(results: Sequence[CopyResult]) -> dict[str, object]:
    n = len(results)
    effect_counts = [len(r.effect_findings) for r in results]
    dose_related = [sum(c.startswith("dose_related") for c in r.effect_findings) for r in results]
    out: dict[str, object] = {
        "copies": n,
        "effect_findings_mean": round(sum(effect_counts) / n, 2) if n else 0.0,
        "effect_findings_max": max(effect_counts, default=0),
        "dose_related_mean": round(sum(dose_related) / n, 2) if n else 0.0,
        "data_quality_per_copy": sorted({len(r.data_quality) for r in results}),
    }
    if any(r.found or r.missed for r in results):
        per_fault: dict[str, list[bool]] = {}
        for r in results:
            for f in r.found:
                per_fault.setdefault(f, []).append(True)
            for f in r.missed:
                per_fault.setdefault(f, []).append(False)
        out["found_rate_by_fault"] = {
            f: round(sum(v) / len(v), 2) for f, v in sorted(per_fault.items())
        }
        out["outlier_raised"] = sum(r.outlier_raised for r in results)
        fps = [len(r.false_positives) for r in results]
        out["false_positives_mean"] = round(sum(fps) / n, 2)
        out["false_positives_max"] = max(fps, default=0)
        targets = sorted(
            {t for r in results for t in r.both_doses_flagged}
            | {f"lb:{t}:{s}:main" for t in ("ALT", "AST") for s in ("M", "F")}
        )
        out["mid_and_high_flagged_rate"] = {
            t: round(sum(t in r.both_doses_flagged for r in results) / n, 2) for t in targets
        }
    return out


def dumps(results: Sequence[CopyResult], extra: Mapping[str, object]) -> str:
    rows = [{s: getattr(r, s) for s in r.__slots__} for r in results]
    return (
        json.dumps(
            {"summary": summarise(results), **extra, "copies": rows},
            indent=2,
            sort_keys=True,
            default=list,
        )
        + "\n"
    )
