"""portfolio.safety_signal_scout through the runner and the API (phase 5 step 3a), on
recorded fake responses (the replay path): the signals view, who sees and who decides,
the ActorWoke naming each response, and a newer scan superseding or retiring."""

from dataclasses import replace
from pathlib import Path
from typing import Any

import structlog
from fastapi.testclient import TestClient

from meridian.agents.catalog import build_registry
from meridian.agents.portfolio.safety_signal_scout import responses_frame
from meridian.agents.runner import AgentRunner, RunReport
from meridian.api.app import create_app
from meridian.domain.enums import Role, Visibility
from meridian.domain.events import Event, EventDraft, SignalScanRequested
from meridian.platform.clock import FixedClock
from meridian.platform.config import Settings
from meridian.portfolio import openfda as o
from meridian.portfolio.store import keep
from meridian.sandbox.executor import InProcessExecutor
from tests.api_support import Fixture, build, headers
from tests.support import T0
from tests.unit.test_signal_scout import TERM_TOTALS, FakeOpenFda


def _scan(fx: Fixture, root: Path, scan_id: str, fake: FakeOpenFda) -> tuple[Event, RunReport]:
    cfg = Settings().agents.safety_signal_scout
    with fx.ledger() as ledger:
        event = ledger.append(
            EventDraft(
                occurred_at=T0,
                actor="meridian.signals",
                study_id="MRD-201",
                visibility=Visibility.BLINDED,
                payload=SignalScanRequested(
                    study_id="MRD-201", scan_id=scan_id, requested_by="karan.mehta"
                ),
            )
        )
        # The responses a live run would have fetched, kept as its inputs (replay path).
        keep(root, event.seq, responses_frame(o.fetch(fake, cfg, sleep=lambda _: None)))
        registry = build_registry(Settings().agents)
        runner = AgentRunner(
            ledger=ledger,
            registry=registry,
            executor=InProcessExecutor(
                registry=registry,
                reader_factory=lambda c: (_ for _ in ()).throw(AssertionError(c)),
                signal_root=root,
                log=structlog.get_logger(),
            ),
            clock=FixedClock(T0),
            study_id="MRD-201",
            log=structlog.get_logger(),
            operational_cuts=(),
            operational_executors=("inprocess",),
            keep_fetched=lambda trigger, records: keep(
                root,
                trigger.seq,
                responses_frame([o.Response(**r.model_dump()) for r in records]),
            ),
        )
        return event, runner.run_pending(agents={"portfolio.safety_signal_scout"})


def _client(fx: Fixture, root: Path) -> TestClient:
    return TestClient(create_app(replace(fx.context(), signal_root=root)))


def _signals(c: TestClient, role: Role, **query: Any) -> list[dict[str, Any]]:
    params = {"agent": "portfolio.safety_signal_scout", "limit": 500, **query}
    items: list[dict[str, Any]] = c.get(
        "/api/v1/findings", params=params, headers=headers(role)
    ).json()["items"]
    return items


def test_the_signals_view_and_who_decides(tmp_path: Path) -> None:
    fx = build(tmp_path / "fx")
    root = tmp_path / "signals"
    event, report = _scan(fx, root, "SCAN-20261120T000000Z", FakeOpenFda())
    assert report.completed == [("portfolio.safety_signal_scout", event.seq)]
    c = _client(fx, root)
    view = c.get("/api/v1/safety/signals", headers=headers(Role.MEDICAL_MONITOR)).json()
    assert view["status"] == "scanned"
    assert (view["data_date"], view["drug_reports"], view["all_reports"]) == (
        "2026-10-28",
        200,
        1_000_000,
    )
    assert [s["term"] for s in view["signals"]] == ["VOMITING", "NAUSEA"]  # by PRR
    nausea = next(s for s in view["signals"] if s["term"] == "NAUSEA")
    assert (nausea["reports"], nausea["term_reports"], nausea["label_listed"]) == (
        50,
        TERM_TOTALS["NAUSEA"],
        True,
    )
    assert nausea["finding_id"] is not None
    assert view["signals_listed"] == 2
    assert [(r["reaction"], r["signal_terms"]) for r in view["label_most_common"]] == [
        ("nausea", ["NAUSEA"]),
        ("dyspepsia", []),
        ("vomiting", ["VOMITING"]),
        ("hypertension", []),
    ]
    assert len(view["caveats"]) == 5
    for role in (Role.CLINICAL_OPS_LEAD, Role.TOXICOLOGIST, Role.QA_AUDITOR):
        assert c.get("/api/v1/safety/signals", headers=headers(role)).status_code == 403
        assert _signals(c, role) == []
    url = f"/api/v1/findings/{nausea['finding_id']}/decisions"
    decision = {"action": "escalated", "reason": "Known from the label; watch in MRD-201."}
    assert c.post(url, json=decision, headers=headers(Role.PORTFOLIO_LEAD)).status_code == 403
    assert c.post(url, json=decision, headers=headers(Role.MEDICAL_MONITOR)).status_code == 201
    woke = [
        e
        for e in c.get(
            "/api/v1/ledger?type=actor_woke&limit=1000", headers=headers(Role.MEDICAL_MONITOR)
        ).json()["entries"]
        if e.get("payload", {}).get("agent_id") == "portfolio.safety_signal_scout"
    ]
    (w,) = woke
    fetched = w["payload"]["fetched"]
    assert len(fetched) == 8
    assert {f["path"] for f in fetched} == {o.EVENT, o.LABEL}
    assert all(len(f["sha256"]) == 64 and f["last_updated"] for f in fetched if f["status"] == 200)


def test_a_newer_scan_supersedes_or_retires(tmp_path: Path) -> None:
    fx = build(tmp_path / "fx")
    root = tmp_path / "signals"
    _scan(fx, root, "SCAN-20261120T000000Z", FakeOpenFda())
    c = _client(fx, root)
    first = {
        s["title"].split(": ", 1)[1].split(" (")[0]: s["finding_id"]
        for s in _signals(c, Role.MEDICAL_MONITOR)
    }
    assert set(first) == {"nausea", "vomiting"}

    class Fewer(FakeOpenFda):
        def __call__(self, path: str, query: str) -> tuple[int, str]:
            status, body = super().__call__(path, query)
            if "VOMITING" in query and "count=fulfillexpeditecriteria" in query:
                return 200, body.replace(str(TERM_TOTALS["VOMITING"]), "200000")
            return status, body

    _scan(fx, root, "SCAN-20261127T000000Z", Fewer("2026-11-25"))
    c = _client(fx, root)
    everything = {
        s["finding_id"]: s
        for s in _signals(c, Role.MEDICAL_MONITOR, include_superseded=True, include_retired=True)
    }
    assert everything[first["nausea"]]["superseded"] is True
    assert everything[first["vomiting"]]["retired"] is True  # no longer a signal
    current = _signals(c, Role.MEDICAL_MONITOR)
    assert [s["title"].split(": ", 1)[1].split(" (")[0] for s in current] == ["nausea"]
    view = c.get("/api/v1/safety/signals", headers=headers(Role.PORTFOLIO_LEAD)).json()
    assert view["data_date"] == "2026-11-25"
    assert view["scan_id"] == "SCAN-20261127T000000Z"
