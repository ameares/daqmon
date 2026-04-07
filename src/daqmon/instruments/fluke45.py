"""Fluke 45 dual-display multimeter driver over serial."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import serial

from .base import InstrumentBase

if TYPE_CHECKING:
    from ..config import ChannelConfig, ScanConfig

logger = logging.getLogger(__name__)

# Canonical function name -> Fluke 45 primary display command mnemonic.
# All of these are also valid for the secondary display (append "2", e.g. "VDC2").
# Primary-only functions (AACDC, VACDC, CONT) are not in this map.
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

    The Fluke 45 has a primary and an optional secondary display.  The scan
    config must contain 1 or 2 channels:

    * Channel 1 → primary display (required)
    * Channel 2 → secondary display (optional)

    All functions in ``FUNC_MAP`` are available on both displays.  Scan timing
    is controlled by ``scan_interval``; ``fetch_sweep`` enforces this interval
    and takes measurements synchronously.

    The range setting only applies to the primary display (channel 1); the
    instrument provides no command to set the secondary display range.

    Instrument-specific options are read from ``channel.extra``:

    * ``rate`` – measurement rate on the primary channel: ``"slow"``,
      ``"medium"`` (default), or ``"fast"``.  The rate command is global and
      affects both displays.
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
        self._primary: Optional[ChannelConfig] = None
        self._secondary: Optional[ChannelConfig] = None
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
        primary, secondary = self._validate_config(scan_cfg)
        self._scan_cfg = scan_cfg
        self._primary = primary
        self._secondary = secondary

        self._raw_write("*RST")
        time.sleep(1.0)
        # *RST may echo or emit a prompt; discard before issuing further commands.
        self._ser.reset_input_buffer()

        # Format 1: numeric-only output (no unit strings), required for float() parsing.
        self._raw_write("FORMAT 1")

        # Primary display: function then range.
        self._raw_write(FUNC_MAP[primary.function.lower()])
        if primary.range == "auto":
            self._raw_write("AUTO")
        else:
            self._raw_write(f"RANGE {primary.range}")

        # Secondary display function (range is not settable for the secondary display).
        if secondary is not None:
            self._raw_write(FUNC_MAP[secondary.function.lower()] + "2")

        # Measurement rate is global; read from the primary channel's extra.
        rate_key = primary.extra.get("rate", "medium")
        rate_cmd = RATE_MAP.get(rate_key, "M")
        self._raw_write(f"RATE {rate_cmd}")

        secondary_info = (
            f"; secondary ch {secondary.channel} ({secondary.name})"
            f" func={FUNC_MAP[secondary.function.lower()]}2"
            if secondary else ""
        )
        logger.info(
            "Fluke 45 configured: primary ch %d (%s) func=%s range=%s rate=%s%s",
            primary.channel, primary.name, FUNC_MAP[primary.function.lower()],
            primary.range, rate_cmd, secondary_info,
        )

    def start(self) -> None:
        self._last_sweep = 0.0  # force an immediate first measurement
        logger.info("Fluke 45 scan started (software-timed)")

    def stop(self) -> None:
        logger.info("Fluke 45 scan stopped")

    def fetch_sweep(self) -> list[tuple[float, int]] | None:
        if self._scan_cfg is None or self._primary is None:
            return None
        if time.monotonic() - self._last_sweep < self._scan_cfg.scan_interval:
            return None

        if self._secondary is None:
            raw = self.query("MEAS1?").strip()
            try:
                value = float(raw)
            except ValueError:
                logger.warning("Fluke 45: could not parse MEAS1? response: %r", raw)
                return None
            self._last_sweep = time.monotonic()
            return [(value, self._primary.channel)]
        else:
            # MEAS? returns both displays in Format 1: "+1.2345E+0,+6.7890E+3<CR><LF>"
            raw = self.query("MEAS?").strip()
            result = self._parse_dual_response(raw)
            if result is None:
                logger.warning("Fluke 45: could not parse MEAS? response: %r", raw)
                return None
            v1, v2 = result
            self._last_sweep = time.monotonic()
            return [(v1, self._primary.channel), (v2, self._secondary.channel)]

    # ------------------------------------------------------------------
    # Validation and parsing helpers (pure logic, no hardware dependency)
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_config(
        scan_cfg: "ScanConfig",
    ) -> tuple["ChannelConfig", "Optional[ChannelConfig]"]:
        """Validate scan config; return (primary, secondary_or_None).

        Raises ValueError if the config is not usable with the Fluke 45.
        """
        n = len(scan_cfg.channels)
        if n == 0 or n > 2:
            raise ValueError(
                f"Fluke 45 supports 1 or 2 channels (primary + optional secondary); "
                f"got {n}"
            )

        ch_map = {ch.channel: ch for ch in scan_cfg.channels}
        invalid = sorted(set(ch_map) - {1, 2})
        if invalid:
            raise ValueError(
                f"Fluke 45 channel numbers must be 1 (primary) and/or 2 (secondary); "
                f"got {sorted(ch_map)}"
            )
        if 1 not in ch_map:
            raise ValueError(
                "Fluke 45 requires channel 1 (primary display); "
                "channel 2 (secondary) is optional"
            )

        primary = ch_map[1]
        secondary = ch_map.get(2)

        if primary.function.lower() not in FUNC_MAP:
            raise ValueError(
                f"Unsupported function for Fluke 45 primary display: {primary.function!r}. "
                f"Supported: {', '.join(FUNC_MAP)}"
            )
        if secondary is not None and secondary.function.lower() not in FUNC_MAP:
            raise ValueError(
                f"Unsupported function for Fluke 45 secondary display: {secondary.function!r}. "
                f"Supported: {', '.join(FUNC_MAP)}"
            )

        return primary, secondary

    @staticmethod
    def _parse_dual_response(raw: str) -> Optional[tuple[float, float]]:
        """Parse a Format-1 ``MEAS?`` response into two float values.

        Format 1 output: ``+1.2345E+0,+6.7890E+3``

        Returns ``None`` if parsing fails.
        """
        parts = raw.strip().split(",")
        if len(parts) != 2:
            return None
        try:
            return float(parts[0]), float(parts[1])
        except ValueError:
            return None

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
