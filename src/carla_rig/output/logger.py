"""Run logger: one CSV row per simulation tick, buffered.

Role in the architecture
------------------------
Writes ``VehicleStatus`` + the applied ``InputState`` to ``runs/<timestamp>/log.csv`` and copies
the fully resolved config to ``runs/<timestamp>/config.yaml`` so every log can be reproduced.

Import rules
------------
stdlib + ``state`` + ``config``. Must NOT import ``carla`` or ``pygame``.

# WHY: (buffered) a disk write can stall for tens of milliseconds (especially on laptops / network
# drives). Doing one per tick would eat the 50 ms budget and cause overruns. We collect rows in
# memory and flush every N rows (TUNE: logging.flush_every_n_rows) and on close.
"""

from __future__ import annotations

import csv
import dataclasses
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from carla_rig.config import Config, dump_config
from carla_rig.state import InputState, VehicleStatus

# Input fields that are useful in the log. One-shot UI flags (toggle_camera, toggle_help, quit)
# are omitted on purpose.
INPUT_FIELDS = ("throttle", "brake", "steer", "blinker", "hand_brake", "reverse", "mouse_steering")


def csv_columns() -> list[str]:
    """Column order: meta, then every VehicleStatus field, then raw input fields prefixed ``in_``."""
    status_cols = [f.name for f in dataclasses.fields(VehicleStatus)]
    # RESEARCH: add experiment columns here (and fill them in RunLogger.write), e.g.
    #   "time_headway_s", "distance_to_lead_m", "trial", "scenario_event".
    return ["wall_time", "participant_id", "condition", *status_cols, *[f"in_{n}" for n in INPUT_FIELDS]]


def make_run_dir(base: str | Path) -> Path:
    """Create ``base/<YYYYmmdd-HHMMSS>`` (with a suffix if two runs start in the same second)."""
    base = Path(base)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = base / stamp
    n = 1
    while run_dir.exists():
        run_dir = base / f"{stamp}-{n}"
        n += 1
    run_dir.mkdir(parents=True)
    return run_dir


class RunLogger:
    """Buffered CSV writer. ``write()`` is cheap; disk I/O happens every N rows."""

    def __init__(self, cfg: Config, run_dir: Optional[Path] = None) -> None:
        log_cfg = cfg.logging
        self.enabled = log_cfg.enabled
        self._flush_every = log_cfg.flush_every_n_rows
        self._participant = log_cfg.participant_id   # RESEARCH: logging.participant_id
        self._condition = log_cfg.condition          # RESEARCH: logging.condition
        self._buffer: list[list[Any]] = []
        self._fh = None
        self._writer = None
        self.run_dir: Optional[Path] = None
        self.rows_written = 0
        if not self.enabled:
            return

        self.run_dir = run_dir or make_run_dir(log_cfg.output_dir)
        # Reproducibility: the exact settings this run used, next to its data.
        dump_config(cfg, self.run_dir / "config.yaml")
        # newline="" is required by the csv module to avoid blank lines on Windows.
        self._fh = (self.run_dir / "log.csv").open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(csv_columns())
        self._fh.flush()  # header on disk immediately, so even a crashed run leaves a valid CSV

    def write(self, status: VehicleStatus, inp: InputState) -> None:
        if not self.enabled:
            return
        row: list[Any] = [f"{time.time():.3f}", self._participant, self._condition]
        row += [getattr(status, f.name) for f in dataclasses.fields(VehicleStatus)]
        row += [getattr(inp, name) for name in INPUT_FIELDS]
        self._buffer.append(row)
        if len(self._buffer) >= self._flush_every:
            self.flush()

    def flush(self) -> None:
        if not self._buffer or self._writer is None:
            return
        self._writer.writerows(self._buffer)
        self._fh.flush()
        self.rows_written += len(self._buffer)
        self._buffer.clear()

    def close(self) -> None:
        """Flush remaining rows and close the file. Idempotent."""
        if self._fh is None:
            return
        try:
            self.flush()
        finally:
            self._fh.close()
            self._fh = None
            self._writer = None
