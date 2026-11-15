"""preclinical.tox_study_monitor 1.0.0: what changed with dose in a repeat-dose study.

Rules: docs/preclinical-eval.md (pre-registered before this code was written). The
analysis is meridian.preclinical.analysis; this module turns each endpoint, sex and phase
that meets a rule into a finding, and each kind of unusable record into a data-quality
finding. Against the concurrent control only. The agent says "dose-related" or "no trend
with dose"; it never judges adversity and never proposes a NOAEL or a LOAEL, which the
toxicologist records (NoaelDecision). One bad record never fails the run.
"""

from collections.abc import Sequence
from typing import Literal

import polars as pl

from meridian.agents.base import AgentContext, FindingDraft, Zone
from meridian.data.study_store import MissingTableError, StudyReader
from meridian.domain.dedup import make_dedup_key
from meridian.domain.enums import EventType, FindingKind, Role, Severity, Visibility
from meridian.domain.events import Event, SendStudyLoaded
from meridian.domain.findings import Evidence
from meridian.platform.agent_settings import ToxStudyMonitorConfig
from meridian.preclinical.analysis import (
    DATA_QUALITY,
    DOSE_RELATED_CHANGE,
    DOSE_RELATED_INCIDENCE,
    MAIN,
    PAIRWISE_CHANGE,
    Analysis,
    GroupStat,
    Problem,
    Summary,
    analyse,
)

AGENT_ID = "preclinical.tox_study_monitor"
VERSION = "1.0.0"
VISIBLE_TO_MAX = frozenset({Role.TOXICOLOGIST, Role.PORTFOLIO_LEAD, Role.QA_AUDITOR})
DOMAINS = ("bg", "bw", "cl", "dd", "dm", "ds", "ex", "fw", "lb", "ma", "mi", "om", "ts", "tx")
SEX = {"M": "males", "F": "females"}
PHASE = {MAIN: "main study", "recovery": "recovery groups"}
PROBLEM_TEXT = {
    "unit_mismatch": "values in a unit other than the one most values of the test use",
    "missing_unit": "numeric values with no unit",
    "duplicate": "more than one value for one animal on one day",
    "control_too_few": "too few control values to compare with",
    "unknown_set": "animals in a set that TX does not define",
    "unknown_sex": "animals with a sex other than M or F",
    "bad_dose": "a set with no numeric dose",
    "control_ambiguous": "no single control group",
    "missing_design": "no DM or TX domain",
}


def _p(p: float | None) -> str:
    if p is None:
        return "not tested"
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}"


def _num(v: float | None) -> str:
    return "n/a" if v is None else f"{v:.4g}"


def _dose(g: GroupStat, unit: str) -> str:
    return "control" if g.rank == 0 else f"{g.dose:g} {unit}"


def _tables(study: StudyReader) -> dict[str, pl.DataFrame]:
    out = {}
    for name in DOMAINS:
        try:
            out[name] = study.table(name)
        except MissingTableError:
            continue
    return out


def _group_evidence(s: Summary, g: GroupStat, unit: str) -> Evidence:
    ep = s.endpoint
    where = f"SEX={s.sex}; PHASE={s.phase}; DOSE={g.dose:g} {unit}"
    if ep.kind == "continuous":
        tail = (
            ""
            if g.rank == 0
            else f", {g.pct:+.0f}%, Dunnett {_p(g.p)}"
            if g.pct is not None
            else ""
        )
        direction: Literal["low", "high", "none"] = (
            "none" if g.rank == 0 or g.pct is None else "high" if g.pct > 0 else "low"
        )
        return Evidence(
            source=f"send:{ep.endpoint.split(':')[0]}",
            selector=where,
            statistic=f"group_mean:{ep.endpoint}",
            value=g.mean if g.mean is not None else 0.0,
            expected=s.groups[0].mean,
            role="primary" if g.flagged else "supporting",
            direction=direction,
            display=f"{_dose(g, unit)}: {_num(g.mean)} {ep.unit} (n = {g.n}{tail})".replace(
                " )", ")"
            ),
        )
    grades = ", ".join(f"grade {grade}: {n}" for grade, n in g.grades)
    sev = f"; {grades}" if grades else ""
    tail = "" if g.rank == 0 else f", Fisher {_p(g.p)}"
    return Evidence(
        source=f"send:{ep.cls}",
        selector=where,
        statistic=f"incidence:{ep.endpoint}",
        value=g.affected / g.n if g.n else 0.0,
        expected=s.groups[0].affected / s.groups[0].n if s.groups[0].n else None,
        role="primary" if g.flagged else "supporting",
        direction="none" if g.rank == 0 else "high",
        display=f"{_dose(g, unit)}: {g.affected} of {g.n}{sev}{tail}",
    )


def _trend_evidence(s: Summary, cfg: ToxStudyMonitorConfig) -> Evidence:
    continuous = s.endpoint.kind == "continuous"
    name = "Jonckheere-Terpstra" if continuous else "Cochran-Armitage"
    alpha = cfg.alpha_trend if continuous else cfg.alpha_incidence_trend
    return Evidence(
        source=f"send:{s.endpoint.endpoint.split(':')[0]}",
        selector=f"SEX={s.sex}; PHASE={s.phase}",
        statistic=f"trend_p:{s.endpoint.endpoint}",
        value=s.trend_p if s.trend_p is not None else 1.0,
        threshold=alpha,
        role="primary"
        if s.check in (DOSE_RELATED_CHANGE, DOSE_RELATED_INCIDENCE)
        else "supporting",
        direction="none",
        display=f"trend across doses {_p(s.trend_p)} ({name})",
    )


def _text(s: Summary, unit: str) -> tuple[str, str]:
    ep = s.endpoint
    who = f"{SEX[s.sex]}, {PHASE[s.phase]}"
    flagged = [g for g in s.groups if g.flagged]
    at = " and ".join(f"{g.dose:g}" for g in flagged) + f" {unit}"
    if ep.kind == "continuous":
        way = "higher" if (flagged[0].pct or 0) > 0 else "lower"
        changes = "; ".join(
            f"{g.dose:g} {unit} {g.pct:+.0f}%" for g in flagged if g.pct is not None
        )
        control = s.groups[0]
        against = f"({changes} against the control mean of {_num(control.mean)} {ep.unit})"
        if s.check == DOSE_RELATED_CHANGE:
            title = f"{ep.label} {way} with dose in {who}"
            lead = f"Dose-related: mean {ep.label} is {way} at {at} {against}"
        else:
            title = f"{ep.label} {way} at {at} in {who}, no trend with dose"
            lead = (
                f"Mean {ep.label} is {way} at {at} {against} with no significant trend across doses"
            )
        rule = (
            "Each flagged group differs from control by Dunnett's test and by at least the "
            "pre-registered magnitude, also without its most extreme animal"
        )
    else:
        control = s.groups[0]
        base = f"control {control.affected} of {control.n}"
        if s.check == DOSE_RELATED_INCIDENCE:
            title = f"{ep.label} more frequent with dose in {who}"
            lead = f"Dose-related: incidence rises with dose ({base})"
        else:
            title = f"{ep.label} more frequent at {at} in {who}, no trend with dose"
            lead = f"Incidence is higher at {at} ({base}) with no significant trend"
        rule = "Incidence against the concurrent control; severity grades are in the evidence"
    summary = (
        f"{lead}. Trend {_p(s.trend_p)}. {rule}. The toxicologist decides what this means "
        "for the NOAEL."
    )
    return title, summary


def _problem_text(p: Problem) -> tuple[str, str, list[Evidence]]:
    what = PROBLEM_TEXT.get(p.kind, p.kind.replace("_", " "))
    where = p.detail.replace(":", " ")
    title = f"Data quality: {where}: {what}"
    effect = (
        "that endpoint is not compared in that sex and phase"
        if p.kind == "control_too_few"
        else "those records are left out; every other record is still analysed"
    )
    summary = f"{p.count} record(s) of {p.domain.upper()} for {where}: {what}; {effect}."
    ev = [
        Evidence(
            source=f"send:{p.domain}",
            selector=f"ENDPOINT={p.detail}",
            statistic=f"data_quality:{p.kind}",
            value=float(p.count),
            role="primary",
            direction="none",
            display=f"{p.count} record(s)",
        ),
    ]
    if p.example:
        ev.append(
            Evidence(
                source=f"send:{p.domain}",
                selector=f"ENDPOINT={p.detail}",
                statistic="data_quality:example",
                value=0.0,
                role="supporting",
                direction="none",
                display=f"for example {p.example}",
            )
        )
    return title, summary, ev


class ToxStudyMonitor:
    agent_id = AGENT_ID
    version = VERSION
    zone = Zone.PRECLINICAL
    subscribes_to = frozenset({EventType.SEND_STUDY_LOADED})
    visibility = Visibility.BLINDED
    visible_to = VISIBLE_TO_MAX
    config_model = ToxStudyMonitorConfig

    def run(
        self, trigger: Event, ctx: AgentContext[ToxStudyMonitorConfig]
    ) -> Sequence[FindingDraft]:
        study, cfg = ctx.study, ctx.config
        if not isinstance(trigger.payload, SendStudyLoaded):
            raise ValueError(f"{AGENT_ID} runs on a SEND study, not on {trigger.payload.type}")
        if trigger.payload.cut_id != study.cut_id:
            raise ValueError(
                f"trigger is for SEND cut {trigger.payload.cut_id}, the reader for {study.cut_id}"
            )
        analysis = analyse(_tables(study), cfg)
        drafts = self.drafts(analysis, cfg, study.study_id, study.cut_id)
        ctx.log.info(
            "tox.analysed",
            endpoints=len(analysis.summaries),
            findings=len(drafts),
            data_quality=len(analysis.problems),
        )
        return drafts

    def drafts(
        self, analysis: Analysis, cfg: ToxStudyMonitorConfig, study_id: str, cut_id: str
    ) -> list[FindingDraft]:
        unit = analysis.design.dose_unit
        out: list[FindingDraft] = []
        for s in analysis.summaries:
            if s.check is None:
                continue
            title, summary = _text(s, unit)
            evidence = [_group_evidence(s, g, unit) for g in s.groups] + [_trend_evidence(s, cfg)]
            dose_related = s.check in (DOSE_RELATED_CHANGE, DOSE_RELATED_INCIDENCE)
            out.append(
                self._draft(
                    cfg,
                    study_id,
                    cut_id,
                    f"{s.check}:{s.key}",
                    title,
                    summary,
                    evidence,
                    Severity.MEDIUM if dose_related else Severity.LOW,
                    1.0 - (s.trend_p if s.trend_p is not None else 1.0),
                )
            )
        for p in analysis.problems:
            title, summary, evidence = _problem_text(p)
            out.append(
                self._draft(
                    cfg, study_id, cut_id, p.check, title, summary, evidence, Severity.LOW, 0.1
                )
            )
        return out

    def _draft(
        self,
        cfg: ToxStudyMonitorConfig,
        study_id: str,
        cut_id: str,
        check: str,
        title: str,
        summary: str,
        evidence: list[Evidence],
        severity: Severity,
        score: float,
    ) -> FindingDraft:
        return FindingDraft(
            dedup_key=make_dedup_key(
                agent_id=AGENT_ID,
                agent_version=VERSION,
                kind=FindingKind.TOX_SIGNAL,
                study_id=study_id,
                site_id=None,
                cut_id=cut_id,
                check=check,
            ),
            kind=FindingKind.TOX_SIGNAL,
            site_id=None,
            severity=severity,
            title=title,
            summary=summary,
            evidence=tuple(evidence),
            score=score,
            visible_to=cfg.visible_to,
        )


__all__ = ["AGENT_ID", "DATA_QUALITY", "PAIRWISE_CHANGE", "VERSION", "ToxStudyMonitor"]
