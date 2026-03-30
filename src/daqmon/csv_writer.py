"""CSV file writer for acquired data points."""

from __future__ import annotations

import csv
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


class CsvWriter:
    """Writes measurement data to a timestamped CSV file in a logs directory.

    Each row represents one sweep; columns are timestamp plus one column per
    channel named "NAME (UNIT)" (or just "NAME" if no unit is defined).
    Column layout is determined from the first batch of readings written.
    """

    def __init__(
        self,
        bucket: str = "daqmon",
        logs_dir: str = "logs",
    ):
        self.bucket = bucket
        self.logs_dir = Path(logs_dir)
        self._file = None
        self._writer: Optional[csv.writer] = None
        self._columns: Optional[list[str]] = None  # set on first write
        self._path: Optional[Path] = None

    def open(self) -> None:
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self._path = self.logs_dir / f"{self.bucket}_{ts}.csv"
        self._file = self._path.open("w", newline="")
        self._writer = csv.writer(self._file)
        logger.info("CSV log file: %s", self._path)

    def close(self) -> None:
        if self._file:
            self._file.close()
            self._file = None
            self._writer = None
            self._columns = None

    def write_readings(self, readings: list[dict[str, Any]]) -> None:
        """Write one sweep row. All readings are expected to share a timestamp."""
        if not self._writer or not readings:
            return

        # Build name -> value mapping for this sweep
        sweep: dict[str, Any] = {}
        ts = readings[0].get("timestamp", datetime.now(timezone.utc))
        for r in readings:
            unit = r.get("unit") or ""
            col = f"{r['name']} ({unit})" if unit else r["name"]
            sweep[col] = r["value"]

        # On the first write, lock in column order and write the header
        if self._columns is None:
            self._columns = list(sweep.keys())
            self._writer.writerow(
                ["timestamp"] + self._columns
            )

        ts_str = ts.isoformat() if isinstance(ts, datetime) else str(ts)
        self._writer.writerow(
            [ts_str] + [sweep.get(col, "") for col in self._columns]
        )
        try:
            self._file.flush()
        except Exception:
            logger.exception("Failed to flush CSV log")
