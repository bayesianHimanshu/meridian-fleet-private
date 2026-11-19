"""The pipeline outlook's rules (phase 5 step 3b; docs/stage-gate-notes.md, "The
outlook"): per asset its risks with their seqs, a status, and the changes since the
previous outlook. Pure: facts in, AssetOutlook out."""

from collections.abc import Sequence

from meridian.domain.enums import Severity
from meridian.domain.events import AssetOutlook, OutlookFact, OutlookRisk
from meridian.portfolio.facts import OPEN, Fact

TOP_RISKS = 5


def _risk(text: str, severity: Severity, rows: Sequence[Fact]) -> OutlookRisk:
    return OutlookRisk(
        text=text,
        severity=severity,
        seqs=tuple(sorted({r.seq for r in rows if r.seq is not None})),
    )


def risks(facts: Sequence[Fact]) -> list[OutlookRisk]:
    def group(g: str) -> list[Fact]:
        return [f for f in facts if f.group == g]

    out: list[OutlookRisk] = []
    preclinical = bool(group("ind_readiness") or group("starting_dose") or group("monitoring"))
    if preclinical and not group("noael"):
        out.append(_risk("No NOAEL decision is recorded", Severity.HIGH, []))
    for f in group("open_finding"):
        if f.severity == "high" and f.status in OPEN:
            out.append(
                _risk(f"High-severity finding {f.finding_id}: {f.label} ({f.status})",
                      Severity.HIGH, [f])
            )  # fmt: skip
    for g, what in (
        ("starting_dose", "dose proposal"),
        ("monitoring", "monitoring recommendation"),
    ):
        for f in group(g):
            if f.status != "accepted":
                out.append(
                    _risk(f"The {what} {f.finding_id or ''} is {f.status or 'not decided'}",
                          Severity.MEDIUM, [f])
                )  # fmt: skip
    gaps = [f for f in group("ind_gap") if f.status in OPEN]
    if gaps:
        out.append(_risk(f"{len(gaps)} IND readiness gap(s) open", Severity.MEDIUM, gaps))
    for f in group("sae_recon"):
        if (f.number or 0) > 0:
            out.append(
                _risk(f"{f.number:g} SAE reconciliation mismatch(es) on {f.value}",
                      Severity.HIGH, [f])
            )  # fmt: skip
    signals = [f for f in group("priority_signal") if f.status in OPEN]
    if signals:
        out.append(
            _risk(f"{len(signals)} priority safety signal(s) not yet reviewed",
                  Severity.MEDIUM, signals)
        )  # fmt: skip
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    out.sort(key=lambda r: (order[r.severity], r.seqs[0] if r.seqs else 0, r.text))
    return out


def _fact(f: Fact) -> OutlookFact:
    return OutlookFact(
        key=f.key,
        group=f.group,
        label=f.label,
        value=f.value,
        status=f.status,
        seq=f.seq,
        static=f.static,
    )


def changes(now: Sequence[OutlookFact], before: Sequence[OutlookFact] | None) -> list[str]:
    if before is None:
        return ["First outlook: nothing to compare with."]
    old = {f.key: f for f in before}
    new = {f.key: f for f in now}
    out = []
    for key in sorted(new.keys() - old.keys()):
        out.append(f"New: {new[key].label}: {new[key].value or new[key].status}")
    for key in sorted(new.keys() & old.keys()):
        a, b = old[key], new[key]
        if (a.value, a.status) != (b.value, b.status):
            out.append(
                f"Changed: {b.label}: {a.value or a.status} ({a.status}) to "
                f"{b.value or b.status} ({b.status})"
            )
    for key in sorted(old.keys() - new.keys()):
        out.append(f"Gone: {old[key].label}: {old[key].value or old[key].status}")
    return out or ["No change since the previous outlook."]


def outlook(
    asset_id: str,
    facts: Sequence[Fact],
    before: Sequence[OutlookFact] | None,
    static_text: str = "",
) -> AssetOutlook:
    mine = [f for f in facts if f.asset_id == asset_id]
    shown = [_fact(f) for f in mine]
    is_static = bool(mine) and all(f.static for f in mine)
    found = risks(mine)
    if is_static:
        status = "static"
        text = static_text or "Static fields only (config/portfolio.toml)"
    elif any(r.severity is Severity.HIGH for r in found):
        status, text = "at_risk", "At risk"
    elif found:
        status, text = "attention", "Needs attention"
    else:
        status, text = "on_track", "On track"
    return AssetOutlook(
        asset_id=asset_id,
        status=status,  # type: ignore[arg-type]
        static=is_static,
        status_text=text,
        facts=tuple(shown),
        risks=tuple(found[:TOP_RISKS]),
        changes=tuple(changes(shown, before)),
    )
