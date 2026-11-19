"""Where the host keeps a signal scan's responses (phase 5 step 3a): the run's inputs, so a
replay gives identical drafts. <signal_root>/<trigger seq>/signal/openfda_responses.parquet,
the same layout the sandbox stages as /stage/signal. Host only."""

from pathlib import Path

import polars as pl

from meridian.data.stage_layout import SIGNAL

RESPONSES_FILE = "openfda_responses.parquet"


def signal_dir(signal_root: Path, trigger_seq: int) -> Path:
    return signal_root / str(trigger_seq)


def keep(signal_root: Path, trigger_seq: int, frame: pl.DataFrame) -> Path:
    """Write the responses once; an existing file must hold the same responses."""
    area = signal_dir(signal_root, trigger_seq) / SIGNAL
    path = area / RESPONSES_FILE
    if path.exists():
        if not pl.read_parquet(path).equals(frame):
            raise ValueError(f"{path} already holds other responses")
        return path
    area.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)
    return path


def kept(signal_root: Path, trigger_seq: int) -> pl.DataFrame | None:
    path = signal_dir(signal_root, trigger_seq) / SIGNAL / RESPONSES_FILE
    return pl.read_parquet(path) if path.exists() else None
