"""The host's side of the two phase 5 step 2 agents' inputs: nothing here runs in a sandbox.

* **NOAEL extract.** preclinical.dose_translation wakes on a NoaelDecision and needs the
  study's decisions up to it; agents never read the ledger, so the host writes them, with
  the run's context (the study and its SEND cut), to <noael_root>/<trigger seq>/noael as
  two parquet tables. That folder is staged as /stage/noael next to the SEND study.
* **Inventory cuts.** The committed inventory CSV is written as a parquet table to
  <inventory_root>/<asset>/<cut>/inventory/studies.parquet, the cut named after the CSV's
  sha256 (a changed inventory is a new cut), and an InventoryLoaded event recorded once:
  preclinical.ind_readiness's trigger.
"""

import hashlib
import os
import shutil
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import polars as pl

from meridian.data.stage_layout import INVENTORY, NOAEL
from meridian.domain.enums import EventType, Visibility
from meridian.domain.events import (
    INVENTORY_CUT_PREFIX,
    Event,
    EventDraft,
    InventoryLoaded,
    NoaelDecision,
)
from meridian.ledger.store import LedgerReader, LedgerWriter
from meridian.preclinical.noael_stage import CONTEXT_TABLE, NOAEL_TABLE, noael_dir
from meridian.preclinical.readiness import INVENTORY_TABLE

_DECISION_SCHEMA = {
    "seq": pl.Int64,
    "decision_id": pl.String,
    "study_id": pl.String,
    "sex": pl.String,
    "established": pl.Boolean,
    "noael_dose": pl.Float64,
    "loael_dose": pl.Float64,
    "dose_unit": pl.String,
    "decided_by": pl.String,
    "supersedes": pl.String,
    "recorded_at": pl.String,
}


def noael_extract(events: Sequence[Event], trigger: Event) -> pl.DataFrame:
    """The study's NOAEL decisions up to and including the trigger, in seq order. Only the
    fields the agent uses: no rationale, no finding ids."""
    assert isinstance(trigger.payload, NoaelDecision)
    study = trigger.payload.study_id
    rows = []
    for e in sorted(events, key=lambda e: e.seq):
        p = e.payload
        if isinstance(p, NoaelDecision) and p.study_id == study and e.seq <= trigger.seq:
            rows.append(
                {
                    "seq": e.seq,
                    "decision_id": p.decision_id,
                    "study_id": p.study_id,
                    "sex": p.sex,
                    "established": p.established,
                    "noael_dose": p.noael_dose,
                    "loael_dose": p.loael_dose,
                    "dose_unit": p.dose_unit,
                    "decided_by": p.decided_by,
                    "supersedes": p.supersedes or "",
                    "recorded_at": e.recorded_at.isoformat(),
                }
            )
    return pl.DataFrame(rows, schema=_DECISION_SCHEMA)


def write_noael_extract(
    events: Sequence[Event], trigger: Event, send_cut: str, noael_root: Path
) -> Path:
    """Write <noael_root>/<seq>/noael/{noael_decisions,noael_context}.parquet, replacing
    any earlier copy for the same trigger. Returns <noael_root>/<seq>."""
    assert isinstance(trigger.payload, NoaelDecision)
    target = noael_dir(noael_root, trigger.seq)
    area = target / NOAEL
    if area.exists():
        shutil.rmtree(area)
    area.mkdir(parents=True)
    noael_extract(events, trigger).write_parquet(area / f"{NOAEL_TABLE}.parquet")
    pl.DataFrame(
        {
            "study_id": [trigger.payload.study_id],
            "send_cut_id": [send_cut],
            "trigger_seq": [trigger.seq],
        }
    ).write_parquet(area / f"{CONTEXT_TABLE}.parquet")
    return target


def inventory_cut_id(csv_bytes: bytes) -> str:
    return INVENTORY_CUT_PREFIX + hashlib.sha256(csv_bytes).hexdigest()[:8]


def inventory_dir(inventory_root: Path, asset_id: str, cut_id: str) -> Path:
    return inventory_root / asset_id / cut_id


def write_inventory(csv_path: Path, inventory_root: Path, asset_id: str) -> tuple[str, Path, str]:
    """Write the CSV as <inventory_root>/<asset>/<cut>/inventory/studies.parquet (every
    column a string, as written). Returns (cut id, cut dir, sha256 of the CSV). The same
    CSV gives the same cut; an existing cut is left as it is."""
    data = csv_path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    cut = inventory_cut_id(data)
    target = inventory_dir(inventory_root, asset_id, cut)
    if (target / INVENTORY / f"{INVENTORY_TABLE}.parquet").exists():
        return cut, target, sha
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(dir=target.parent, prefix=".tmp-"))
    try:
        (tmp / INVENTORY).mkdir()
        frame = pl.read_csv(csv_path, infer_schema=False)
        frame.write_parquet(tmp / INVENTORY / f"{INVENTORY_TABLE}.parquet")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    return cut, target, sha


def inventory_events(reader: LedgerReader, asset_id: str | None = None) -> list[Event]:
    out = []
    for e in reader.read(event_types=[EventType.INVENTORY_LOADED]):
        if (
            isinstance(e, Event)
            and isinstance(e.payload, InventoryLoaded)
            and (asset_id is None or e.payload.asset_id == asset_id)
        ):
            out.append(e)
    return out


def record_inventory(
    ledger: LedgerReader,
    writer: LedgerWriter,
    *,
    occurred_at: datetime,
    actor: str,
    asset_id: str,
    cut_id: str,
    path: Path,
    source_sha256: str,
) -> tuple[Event, bool]:
    """Append InventoryLoaded once per (asset, cut). Returns (event, appended)."""
    for e in inventory_events(ledger, asset_id):
        assert isinstance(e.payload, InventoryLoaded)
        if e.payload.cut_id == cut_id:
            return e, False
    event = writer.append(
        EventDraft(
            occurred_at=occurred_at,
            actor=actor,
            study_id=asset_id,
            visibility=Visibility.BLINDED,
            payload=InventoryLoaded(
                asset_id=asset_id,
                cut_id=cut_id,
                path=path.as_posix(),
                source_sha256=source_sha256,
            ),
        )
    )
    return event, True
