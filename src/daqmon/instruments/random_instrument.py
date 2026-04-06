"""Random-number instrument for testing and demonstration.

This instrument requires no hardware.  It generates Gaussian random values
for each configured channel on every sweep, respecting ``scan_interval``
timing the same way a real software-timed device would.

Usage in a scan config JSON::

    {
      "instrument_type": "random",
      "description": "Random demo",
      "scan_interval": 2.0,
      "channels": [
        {"channel": 1, "name": "signal_a", "unit": "V",
         "extra": {"mean": 5.0, "std": 0.1}},
        {"channel": 2, "name": "signal_b", "unit": "mA",
         "extra": {"mean": 100.0, "std": 2.0}},
        {"channel": 3, "name": "temperature", "unit": "C",
         "extra": {"mean": 25.0, "std": 0.5}}
      ]
    }

Channel-specific ``extra`` keys:

* ``mean``  – centre of the Gaussian distribution (default ``0.0``)
* ``std``   – standard deviation (default ``1.0``)
"""

from __future__ import annotations

import logging
import random
import time
from typing import TYPE_CHECKING, Optional

from .base import InstrumentBase

if TYPE_CHECKING:
    from ..config import ScanConfig

logger = logging.getLogger(__name__)


class RandomInstrument(InstrumentBase):
    """Multi-channel Gaussian random-number generator.

    Implements the full :class:`~daqmon.instruments.base.InstrumentBase`
    interface so it can be dropped in wherever a real instrument is expected.
    No serial port or hardware is required.

    The constructor accepts (and ignores) ``port``, ``baudrate``, and
    ``timeout`` so the standard registry factory works without special-casing.
    """

    def __init__(
        self,
        port: str = "",
        baudrate: int = 0,
        timeout: float = 10.0,
        seed: Optional[int] = None,
    ):
        self._rng = random.Random(seed)
        self._scan_cfg: Optional[ScanConfig] = None
        self._last_sweep: float = 0.0
        self._started: bool = False

    # ------------------------------------------------------------------
    # InstrumentBase implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        logger.info("RandomInstrument: open (no hardware)")

    def close(self) -> None:
        logger.info("RandomInstrument: close (no hardware)")

    def idn(self) -> str:
        return "RANDOM,RandomInstrument,SN000000,FW1.0"

    def configure(self, scan_cfg: "ScanConfig") -> None:
        self._scan_cfg = scan_cfg
        logger.info(
            "RandomInstrument configured: %d channels, interval=%.1fs",
            len(scan_cfg.channels),
            scan_cfg.scan_interval,
        )
        for ch in scan_cfg.channels:
            mean = ch.extra.get("mean", 0.0)
            std = ch.extra.get("std", 1.0)
            logger.info(
                "  ch %d (%s): mean=%.3g std=%.3g unit=%s",
                ch.channel, ch.name, mean, std, ch.unit,
            )

    def start(self) -> None:
        self._last_sweep = 0.0  # trigger an immediate first sweep
        self._started = True
        logger.info("RandomInstrument started")

    def stop(self) -> None:
        self._started = False
        logger.info("RandomInstrument stopped")

    def fetch_sweep(self) -> list[tuple[float, int]] | None:
        if not self._started or self._scan_cfg is None:
            return None
        if time.monotonic() - self._last_sweep < self._scan_cfg.scan_interval:
            return None

        sweep = []
        for ch in self._scan_cfg.channels:
            mean = float(ch.extra.get("mean", 0.0))
            std = float(ch.extra.get("std", 1.0))
            value = self._rng.gauss(mean, std)
            sweep.append((value, ch.channel))

        self._last_sweep = time.monotonic()
        return sweep
