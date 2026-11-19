"""The outlook's rules (phase 5 step 3b; docs/stage-gate-notes.md) and the report codec."""

from meridian.domain.enums import FindingKind
from meridian.domain.events import GatePack, OutlookFact, PortfolioOutlook
from meridian.portfolio.facts import Fact
from meridian.portfolio.outlook import changes, outlook
from meridian.portfolio.reports import draft, payload

A = "MRD-101"


def test_status_follows_the_most_severe_risk() -> None:
    ok = [Fact(A, "noael", "noael:M", "NOAEL (M)", "2 mg/kg/day", "established", seq=1),
          Fact(A, "starting_dose", "dose", "Dose", "1.94 mg", "accepted", seq=2),
          Fact(A, "ind_readiness", "ind", "IND", "100%", "assessed", seq=3)]  # fmt: skip
    assert outlook(A, ok, None).status == "on_track"
    gap = [*ok, Fact(A, "ind_gap", "g1", "Gap", "", "open", "medium", 4, "PRE-1")]
    o = outlook(A, gap, None)
    assert (o.status, [r.seqs for r in o.risks]) == ("attention", [(4,)])
    high = [*gap, Fact(A, "open_finding", "f", "Necrosis", "", "escalated", "high", 5, "PRE-2")]
    o = outlook(A, high, None)
    assert o.status == "at_risk"
    assert o.risks[0].severity.value == "high"  # high before medium
    no_noael = [f for f in ok if f.group != "noael"]
    assert outlook(A, no_noael, None).risks[0].text == "No NOAEL decision is recorded"
    static = [Fact("MRD-110", "static", "static:status_text", "Status", "On track", "static",
                   static=True)]  # fmt: skip
    s = outlook("MRD-110", static, None, "On track")
    assert (s.status, s.static, s.status_text, s.risks) == ("static", True, "On track", ())


def test_changes_against_the_previous_outlook() -> None:
    def f(key: str, value: str, status: str = "open") -> OutlookFact:
        return OutlookFact(key=key, group="g", label=key, value=value, status=status, seq=1)

    assert changes([f("a", "1")], None) == ["First outlook: nothing to compare with."]
    assert changes([f("a", "1")], [f("a", "1")]) == ["No change since the previous outlook."]
    got = changes([f("a", "2", "accepted"), f("b", "x")], [f("a", "1"), f("c", "y")])
    assert got == ["New: b: x", "Changed: a: 1 (open) to 2 (accepted)", "Gone: c: y"]


def test_a_report_draft_round_trips_into_its_event() -> None:
    body: dict[str, object] = {"review_id": "REVIEW-20261120T000000Z",
                               "previous_outlook_seq": None, "assets": []}  # fmt: skip
    d = draft(FindingKind.PORTFOLIO_OUTLOOK, "k", "t", "s", body)
    event = payload(d, "portfolio.pipeline_intelligence", "1.0.0", 7)
    assert isinstance(event, PortfolioOutlook)
    assert (event.trigger_seq, event.dedup_key, event.summary) == (7, "k", "s")
    pack = draft(FindingKind.GATE_PACK, "k2", "t", "s", {
        "gate_request_id": "GATE-20261120T000000Z", "asset_id": A, "gate": "ind_submission",
        "gate_title": "IND submission", "criteria": [], "open_items": []})  # fmt: skip
    assert isinstance(payload(pack, "portfolio.stage_gate_pack", "1.0.0", 8), GatePack)
