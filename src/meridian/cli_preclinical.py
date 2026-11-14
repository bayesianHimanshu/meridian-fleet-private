"""meridian preclinical: MRD-101's SEND study and preclinical.tox_study_monitor."""

import httpx
import typer

from meridian.data.cut_writer import CutExistsError
from meridian.data.fetch import FetchError, fetch
from meridian.data.send import SendIngestError, check_pinned, ingest_send
from meridian.platform.config import Settings
from meridian.platform.container import Container

preclinical_app = typer.Typer(
    no_args_is_help=True,
    help="MRD-101's SEND study (docs/preclinical-data.md) and its toxicology agent.",
)


def _fail(exc: Exception) -> typer.Exit:
    typer.echo(f"error: {exc}", err=True)
    return typer.Exit(code=1)


@preclinical_app.command("fetch")
def preclinical_fetch() -> None:
    """Download the pinned SEND files once and check each against its pinned sha256."""
    with Container.build(Settings()) as c:
        p = c.settings.preclinical
        try:
            with httpx.Client(
                follow_redirects=True, timeout=p.timeout_seconds, trust_env=True
            ) as client:
                report = fetch(
                    client=client,
                    clock=c.clock,
                    base_url=p.base_url,
                    domains=sorted(p.files),
                    raw_dir=p.raw_dir,
                )
            check_pinned(p.raw_dir, p.files)
        except (FetchError, SendIngestError, httpx.HTTPError, OSError) as exc:
            raise _fail(exc) from exc
        for name, entry in sorted(report.manifest.files.items()):
            state = "downloaded" if name in report.downloaded else "unchanged"
            typer.echo(f"{name:<8} {entry.size_bytes:>9} bytes  sha256 {entry.sha256}  {state}")
        typer.echo(f"all {len(p.files)} files match their pinned sha256")


@preclinical_app.command("ingest")
def preclinical_ingest() -> None:
    """Curate the fetched study into <send_root>/<study>/<cut> and record SendStudyLoaded."""
    with Container.build(Settings()) as c:
        p = c.settings.preclinical
        try:
            result = ingest_send(
                raw_dir=p.raw_dir,
                pinned=p.files,
                send_root=p.send_root,
                study_id=p.study_id,
                cut_id=p.cut_id,
                source_study_id=p.source_study_id,
                treatment=p.treatment,
                source_treatment=p.source_treatment,
                ledger=c.ledger,
                occurred_at=c.clock.now(),
            )
        except (SendIngestError, CutExistsError, OSError) as exc:
            raise _fail(exc) from exc
        state = "written" if result.cut.created else "already present, identical"
        typer.echo(f"SEND cut {p.study_id}/{p.cut_id} {state} at {result.cut.path}")
        for f in result.cut.manifest.files:
            typer.echo(f"  {f.path:<20} {f.rows:>6} rows  sha256 {f.sha256[:16]}")
        verb = "appended" if result.event_appended else "already recorded"
        typer.echo(f"SendStudyLoaded {verb} at ledger seq {result.event.seq}")
