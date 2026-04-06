"""Fluke 45 dual-display multimeter driver over serial."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import serial

from .base import InstrumentBase

if TYPE_CHECKING:
    from ..config import ScanConfig

logger = logging.getLogger(__name__)

# Canonical function name -> Fluke 45 function-select mnemonic
FUNC_MAP = {
    "dc_voltage":    "VDC",
    "ac_voltage":    "VAC",
    "dc_current":    "ADC",
    "ac_current":    "AAC",
    "resistance_2w": "OHMS",
    "frequency":     "FREQ",
    "diode":         "DIODE",
}

# Measurement rate: our canonical name -> Fluke 45 RATE keyword
RATE_MAP = {
    "slow":   "S",
    "medium": "M",
    "fast":   "F",
}


class Fluke45(InstrumentBase):
    """Driver for the Fluke 45 dual-display multimeter.

    Serial settings: 9600 baud, 8N1, no flow control.

    The Fluke 45 is a single-channel, software-timed instrument.  The scan
    config must contain exactly one channel.  Scan timing is controlled by
    ``scan_interval`` in the config; ``fetch_sweep`` enforces this interval
    and takes the measurement synchronously.

    Instrument-specific options are read from ``channel.extra``:

    * ``rate`` – measurement rate: ``"slow"``, ``"medium"`` (default),
      or ``"fast"``.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 10.0,
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: Optional[serial.Serial] = None
        self._scan_cfg: Optional[ScanConfig] = None
        self._last_sweep: float = 0.0

    # ------------------------------------------------------------------
    # InstrumentBase implementation
    # ------------------------------------------------------------------

    def open(self) -> None:
        logger.info("Opening serial port %s @ %d baud (Fluke 45)", self.port, self.baudrate)
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        # Send device clear (RS-232 ^C = IEEE-488 DCL) to abort any pending
        # operation and get into a known state, then drain whatever the meter
        # echoes back (prompt, partial response, etc.).
        self._ser.write(b"\x03")
        time.sleep(0.2)
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            logger.info("Closing serial port %s", self.port)
            self._ser.close()

    def idn(self) -> str:
        return self.query("*IDN?")

    def configure(self, scan_cfg: "ScanConfig") -> None:
        if len(scan_cfg.channels) != 1:
            raise ValueError(
                f"Fluke 45 supports exactly one channel per scan config; "
                f"got {len(scan_cfg.channels)}"
            )
        self._scan_cfg = scan_cfg
        ch = scan_cfg.channels[0]

        self._raw_write("*RST")
        time.sleep(1.0)
        # *RST may echo or emit a prompt; discard before issuing further commands.
        self._ser.reset_input_buffer()

        # Ensure numeric-only output (Format 1). Format 2 appends unit strings
        # like "VDC" which would break float() parsing of MEAS1? responses.
        self._raw_write("FORMAT 1")

        func = FUNC_MAP.get(ch.function.lower())
        if func is None:
            raise ValueError(
                f"Unsupported function for Fluke 45: {ch.function!r}. "
                f"Supported: {', '.join(FUNC_MAP)}"
            )
        # Function is selected by sending its mnemonic directly (e.g. "VDC"),
        # not via a "FUNC1 <mnemonic>" prefix command.
        self._raw_write(func)

        # Range: "AUTO" command enters autoranging; "RANGE <n>" sets a fixed
        # integer range (1–7).  RANGE1 is a query-only keyword, not a setter.
        if ch.range == "auto":
            self._raw_write("AUTO")
        else:
            self._raw_write(f"RANGE {ch.range}")

        rate_key = ch.extra.get("rate", "medium")
        rate_cmd = RATE_MAP.get(rate_key, "M")
        self._raw_write(f"RATE {rate_cmd}")

        logger.info(
            "Fluke 45 configured: ch %d (%s) func=%s range=%s rate=%s",
            ch.channel, ch.name, func, ch.range, rate_cmd,
        )

    def start(self) -> None:
        self._last_sweep = 0.0  # force an immediate first measurement
        logger.info("Fluke 45 scan started (software-timed)")

    def stop(self) -> None:
        logger.info("Fluke 45 scan stopped")

    def fetch_sweep(self) -> list[tuple[float, int]] | None:
        if self._scan_cfg is None:
            return None
        scan_interval = self._scan_cfg.scan_interval
        if time.monotonic() - self._last_sweep < scan_interval:
            return None

        ch = self._scan_cfg.channels[0]
        raw = self.query("MEAS1?").strip()
        try:
            value = float(raw)
        except ValueError:
            logger.warning("Fluke 45: could not parse measurement response: %r", raw)
            return None

        self._last_sweep = time.monotonic()
        logger.debug("Fluke 45 measurement: ch %d = %g", ch.channel, value)
        return [(value, ch.channel)]

    # ------------------------------------------------------------------
    # Low-level serial I/O
    # ------------------------------------------------------------------

    def _raw_write(self, cmd: str) -> None:
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        logger.debug("TX >>> %s", cmd)
        self._ser.write((cmd + "\r\n").encode("ascii"))

    def query(self, cmd: str) -> str:
        self._raw_write(cmd)
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        resp = self._ser.readline().decode("ascii", errors="replace").strip()
        logger.debug("RX <<< %s", resp)
        return resp
