"""The preclinical evaluation harness (docs/preclinical-eval.md): permutation keeps group
sizes and TK animals, planting records its faults, ground truth is never rewritten."""

from pathlib import Path

import polars as pl
import pytest

from meridian.evals.preclinical import CHANGE, evaluate_set, permute, plant
from meridian.preclinical.analysis import read_design
from meridian.preclinical.inprocess import run_checks
from meridian.preclinical.synth import StudySpec, build
from tests.tox_support import config

RUN = run_checks(config(), "SYN-TOX-01")


def _sizes(tables: dict[str, pl.DataFrame]) -> list[tuple[object, ...]]:
    d = read_design(tables["dm"], tables["tx"], tables["ds"])
    return sorted(d.animals.group_by(["phase", "SEX", "rank"], maintain_order=True).len().rows())


def test_a_permutation_moves_labels_within_sex_and_phase_only() -> None:
    base = build(StudySpec(seed=51, recovery=True))
    shuffled = permute(base, 1)
    assert _sizes(shuffled) == _sizes(base)
    assert (shuffled["dm"]["SETCD"] != base["dm"]["SETCD"]).sum() > 0
    assert shuffled["dm"].select("USUBJID", "SEX").equals(base["dm"].select("USUBJID", "SEX"))
    joined = shuffled["dm"].join(base["dm"], on="USUBJID", suffix="_base")
    assert (joined["SETCD"].str.ends_with("R") == joined["SETCD_base"].str.ends_with("R")).all()
    assert permute(base, 1)["dm"].equals(shuffled["dm"])  # seeded


def test_planting_records_one_fault_per_effect_and_sex() -> None:
    planted = plant(permute(build(StudySpec(seed=52)), 2), 2)
    kinds = sorted({f.fault_type for f in planted.faults})
    assert kinds == [
        "bw_gain_decrease",
        "consequence",
        "incidence_increase",
        "lb_increase",
        "organ_weight_increase",
        "outlier_single_animal",
    ]
    assert [f.target for f in planted.faults if f.kri is None] == ["lb:CREAT:M:main"]
    assert {f.kri for f in planted.faults if f.fault_type == "lb_increase"} == {CHANGE}
    hyper = planted.tables["mi"].filter(pl.col("MISTRESC") == "HYPERTROPHY")
    assert hyper.height == 2 * (3 + 8)


def test_ground_truth_is_written_once_and_never_rewritten(tmp_path: Path) -> None:
    base = build(StudySpec(seed=53))
    evaluate_set("dev", base, config(), RUN, "0" * 64, tmp_path)
    first = {p.name: p.read_text() for p in tmp_path.glob("*.json")}
    assert len(first) == 10
    evaluate_set("dev", base, config(), RUN, "0" * 64, tmp_path)
    assert {p.name: p.read_text() for p in tmp_path.glob("*.json")} == first
    with pytest.raises(ValueError, match="never rewritten"):
        evaluate_set("dev", base, config(), RUN, "f" * 64, tmp_path)
