"""HP 34970A SCPI instrument driver over serial."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Optional

import serial

from .base import InstrumentBase

if TYPE_CHECKING:
    from ..config import ChannelConfig, ScanConfig

logger = logging.getLogger(__name__)

# Canonical name -> SCPI subsystem keyword
FUNC_MAP = {
    "dc_voltage":    "VOLT:DC",
    "ac_voltage":    "VOLT:AC",
    "dc_current":    "CURR:DC",
    "ac_current":    "CURR:AC",
    "resistance_2w": "RES",
    "resistance_4w": "FRES",
    "frequency":     "FREQ",
    "period":        "PER",
    "temperature":   "TEMP",
    "digital_input": "DIG",
    "totalize":      "TOT",
}

TC_TYPE_MAP = {
    "J": "J", "K": "K", "T": "T", "E": "E",
    "R": "R", "S": "S", "B": "B", "N": "N",
}

RANGE_MAP = {
    "auto":  "DEF",
    "0.1":   "0.1",
    "1":     "1",
    "10":    "10",
    "100":   "100",
    "300":   "300",
}

# Reverse: SCPI float -> clean string
_RANGE_FLOAT_TO_CLEAN: dict[float, str] = {
    float(k): v for k, v in RANGE_MAP.items() if k != "auto"
}

# Map from ref-junction SCPI response to our canonical name
_RJUN_SCPI_TO_KEY = {
    "INT":  "internal",
    "FIX":  "fixed",
    "EXT":  "external",
}


def normalize_range(raw: str) -> str:
    """Convert a raw SCPI range response like '+1.00000000E-01' to '0.1', or 'auto'."""
    raw = raw.strip()
    if not raw:
        return "auto"
    try:
        val = float(raw)
    except ValueError:
        return "auto"
    if val <= 0:
        return "auto"
    clean = _RANGE_FLOAT_TO_CLEAN.get(val)
    if clean:
        return clean
    if val == int(val):
        return str(int(val))
    return f"{val:g}"


class HP34970A(InstrumentBase):
    """Driver for the HP/Agilent 34970A Data Acquisition / Switch Unit."""

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        baudrate: int = 9600,
        timeout: float = 10.0,
        read_termination: str = "\n",
        write_termination: str = "\n",
    ):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.read_term = read_termination
        self.write_term = write_termination
        self._ser: Optional[serial.Serial] = None
        self._scan_cfg: Optional[ScanConfig] = None

    # ------------------------------------------------------------------
    # InstrumentBase implementation
    # ------------------------------------------------------------------

    def configure(self, scan_cfg: "ScanConfig") -> None:
        """Apply full scan configuration to the instrument."""
        self._scan_cfg = scan_cfg
        self.reset()
        self.clear_status()
        time.sleep(0.5)

        for ch in scan_cfg.channels:
            self._configure_channel(ch)

        self.set_scan_list(scan_cfg.channel_numbers)
        self.set_scan_interval(scan_cfg.scan_interval)
        self.set_scan_count(scan_cfg.scan_count)
        self.enable_channel_in_readings()

        logger.info(
            "Scan configured: %d channels, interval=%.1fs, count=%s",
            len(scan_cfg.channels),
            scan_cfg.scan_interval,
            "infinite" if scan_cfg.scan_count <= 0 else scan_cfg.scan_count,
        )

    def start(self) -> None:
        """Initiate the internal scan engine."""
        self.initiate_scan()

    def stop(self) -> None:
        """Abort the running scan."""
        try:
            self.abort_scan()
        except Exception:
            pass

    def fetch_sweep(self) -> list[tuple[float, int]] | None:
        """Return the latest complete sweep from the instrument buffer, or None.

        If more than one sweep has accumulated (poll interval too slow), the
        excess sweeps are discarded and a warning is logged.
        """
        if self._scan_cfg is None:
            return None
        n_channels = len(self._scan_cfg.channels)
        available = self.get_data_count()
        if available < n_channels:
            return None

        n_complete = available // n_channels
        if n_complete > 1:
            logger.warning(
                "Data loss: %d sweeps accumulated (expected 1); "
                "discarding all but the latest",
                n_complete,
            )
        raw = self.query_readings_with_channels(
            f"DATA:REM? {n_complete * n_channels}"
        )
        if not raw:
            return None
        return raw[-n_channels:]

    # ------------------------------------------------------------------
    # Low-level serial I/O
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the serial port."""
        logger.info("Opening serial port %s @ %d baud", self.port, self.baudrate)
        self._ser = serial.Serial(
            port=self.port,
            baudrate=self.baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=self.timeout,
            xonxoff=True,
            rtscts=False,
            dsrdtr=False,
        )
        self._ser.reset_input_buffer()
        self._ser.reset_output_buffer()
        time.sleep(0.2)

    def close(self) -> None:
        if self._ser and self._ser.is_open:
            logger.info("Closing serial port %s", self.port)
            self._ser.close()

    def _raw_write(self, cmd: str) -> None:
        """Send bytes on the wire – no *OPC? sync."""
        if not self._ser or not self._ser.is_open:
            raise RuntimeError("Serial port not open")
        logger.debug("TX >>> %s", cmd)
        self._ser.write((cmd + self.write_term).encode("ascii"))

    def write(self, cmd: str) -> None:
        """Send a SCPI command and block until *OPC? returns '1'."""
        self._raw_write(cmd)
        self._raw_write("*OPC?")
        opc = self._ser.readline().decode("ascii", errors="replace").strip()
        if opc != "1":
            logger.warning("*OPC? returned %r after cmd %r", opc, cmd)

    def query(self, cmd: str) -> str:
        """Send a SCPI query and return the response string."""
        self._raw_write(cmd)
        resp = self._ser.readline().decode("ascii", errors="replace").strip()
        logger.debug("RX <<< %s", resp)
        return resp

    def query_values(self, cmd: str) -> list[float]:
        """Send a query and parse a comma-separated list of floats."""
        resp = self.query(cmd)
        if not resp:
            return []
        values = []
        for p in resp.split(","):
            try:
                values.append(float(p.strip()))
            except ValueError:
                logger.warning("Could not parse value: %r", p)
        return values

    def query_readings_with_channels(self, cmd: str) -> list[tuple[float, int]]:
        """Parse alternating value/channel pairs from a DATA:REM? response.

        With FORM:READ:CHAN ON, returns (measured_value, channel_number) tuples.
        """
        resp = self.query(cmd)
        if not resp:
            return []
        parts = resp.split(",")
        results = []
        for i in range(0, len(parts) - 1, 2):
            try:
                results.append(
                    (float(parts[i].strip()), int(float(parts[i + 1].strip())))
                )
            except ValueError:
                logger.warning(
                    "Could not parse reading pair at index %d: %r, %r",
                    i, parts[i], parts[i + 1],
                )
        return results

    def idn(self) -> str:
        """Return the *IDN? response."""
        return self.query("*IDN?")

    def reset(self) -> None:
        """Reset instrument to factory defaults (*RST is slow; wait then sync)."""
        self._raw_write("*RST")
        time.sleep(2.0)
        self._raw_write("*OPC?")
        opc = self._ser.readline().decode("ascii", errors="replace").strip()
        if opc != "1":
            logger.warning("*OPC? after *RST returned %r", opc)

    def clear_status(self) -> None:
        self.write("*CLS")

    def _chan_list(self, channels: list[int]) -> str:
        return "(@" + ",".join(str(c) for c in channels) + ")"

    # ------------------------------------------------------------------
    # Channel configuration helpers (used by configure())
    # ------------------------------------------------------------------

    def _configure_channel(self, ch: "ChannelConfig") -> None:
        """Apply a single channel's measurement configuration to the instrument."""
        chans = [ch.channel]
        func = ch.function.lower()

        if func == "dc_voltage":
            self.configure_dc_voltage(chans, range_val=ch.range, nplc=ch.nplc)
        elif func == "ac_voltage":
            self.configure_ac_voltage(chans, range_val=ch.range, ac_bandwidth=ch.ac_bandwidth)
        elif func == "dc_current":
            self.configure_dc_current(chans, range_val=ch.range, nplc=ch.nplc)
        elif func == "ac_current":
            self.configure_ac_current(chans, range_val=ch.range, ac_bandwidth=ch.ac_bandwidth)
        elif func == "resistance_2w":
            self.configure_resistance_2w(chans, range_val=ch.range, nplc=ch.nplc)
        elif func == "resistance_4w":
            self.configure_resistance_4w(chans, range_val=ch.range, nplc=ch.nplc)
        elif func == "frequency":
            self.configure_frequency(chans, range_val=ch.range)
        elif func == "period":
            self.configure_period(chans, range_val=ch.range)
        elif func in ("temperature", "thermocouple"):
            self.configure_thermocouple(
                chans,
                tc_type=ch.tc_type,
                ref_junction=ch.ref_junction,
                ref_channel=ch.ref_channel,
                ref_fixed_temp=ch.ref_fixed_temp,
                nplc=ch.nplc,
            )
        elif func == "digital_input":
            self.configure_digital_input(chans)
        elif func == "totalize":
            self.configure_totalizer(chans)
        else:
            logger.warning(
                "Unknown function '%s' for channel %d – skipping", func, ch.channel
            )
            return

        if ch.delay is not None:
            self.set_channel_delay(ch.channel, ch.delay)

        logger.info(
            "Configured ch %d (%s) as %s range=%s nplc=%.1f",
            ch.channel, ch.name, func, ch.range, ch.nplc,
        )

    # ------------------------------------------------------------------
    # SCPI measurement configuration commands
    # ------------------------------------------------------------------

    def configure_dc_voltage(
        self, channels: list[int], range_val: str = "auto", nplc: float = 1.0
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:VOLT:DC {rng},{cl}")
        self.write(f"VOLT:DC:NPLC {nplc},{cl}")

    def configure_ac_voltage(
        self, channels: list[int], range_val: str = "auto",
        ac_bandwidth: Optional[float] = None,
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:VOLT:AC {rng},{cl}")
        if ac_bandwidth is not None:
            self.write(f"VOLT:AC:BAND {ac_bandwidth:g},{cl}")

    def configure_dc_current(
        self, channels: list[int], range_val: str = "auto", nplc: float = 1.0
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:CURR:DC {rng},{cl}")
        self.write(f"CURR:DC:NPLC {nplc},{cl}")

    def configure_ac_current(
        self, channels: list[int], range_val: str = "auto",
        ac_bandwidth: Optional[float] = None,
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:CURR:AC {rng},{cl}")
        if ac_bandwidth is not None:
            self.write(f"CURR:AC:BAND {ac_bandwidth:g},{cl}")

    def configure_resistance_2w(
        self, channels: list[int], range_val: str = "auto", nplc: float = 1.0
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:RES {rng},{cl}")
        self.write(f"RES:NPLC {nplc},{cl}")

    def configure_resistance_4w(
        self, channels: list[int], range_val: str = "auto", nplc: float = 1.0
    ) -> None:
        cl = self._chan_list(channels)
        rng = RANGE_MAP.get(range_val, "DEF")
        self.write(f"CONF:FRES {rng},{cl}")
        self.write(f"FRES:NPLC {nplc},{cl}")

    def configure_frequency(self, channels: list[int], range_val: str = "auto") -> None:
        cl = self._chan_list(channels)
        self.write(f"CONF:FREQ {RANGE_MAP.get(range_val, 'DEF')},{cl}")

    def configure_period(self, channels: list[int], range_val: str = "auto") -> None:
        cl = self._chan_list(channels)
        self.write(f"CONF:PER {RANGE_MAP.get(range_val, 'DEF')},{cl}")

    def configure_thermocouple(
        self,
        channels: list[int],
        tc_type: str = "K",
        ref_junction: str = "internal",
        ref_channel: Optional[int] = None,
        ref_fixed_temp: Optional[float] = None,
        nplc: float = 1.0,
    ) -> None:
        cl = self._chan_list(channels)
        tct = TC_TYPE_MAP.get(tc_type.upper(), "K")
        self.write(f"CONF:TEMP TC,{tct},{cl}")
        self.write(f"TEMP:NPLC {nplc},{cl}")
        if ref_junction.lower() == "internal":
            self.write(f"TEMP:TRAN:TC:RJUN:TYPE INT,{cl}")
        elif ref_junction.lower() == "fixed":
            self.write(f"TEMP:TRAN:TC:RJUN:TYPE FIX,{cl}")
            if ref_fixed_temp is not None:
                self.write(f"TEMP:TRAN:TC:RJUN:FIX {ref_fixed_temp:.3f},{cl}")
        elif ref_junction.lower() == "external" and ref_channel is not None:
            self.write(f"TEMP:TRAN:TC:RJUN:TYPE EXT,{cl}")

    def configure_digital_input(self, channels: list[int]) -> None:
        cl = self._chan_list(channels)
        self.write(f"CONF:DIG:BYTE {cl}")

    def configure_totalizer(self, channels: list[int]) -> None:
        cl = self._chan_list(channels)
        self.write(f"CONF:TOT {cl}")

    # ------------------------------------------------------------------
    # Scan control
    # ------------------------------------------------------------------

    def set_scan_list(self, channels: list[int]) -> None:
        cl = self._chan_list(channels)
        self.write(f"ROUT:SCAN {cl}")
        logger.info("Scan list set: %s", cl)

    def set_scan_count(self, count: int = 0) -> None:
        """Set scan sweeps; 0 = infinite."""
        self.write("TRIG:COUNT INF" if count <= 0 else f"TRIG:COUNT {count}")

    def set_scan_interval(self, seconds: float = 10.0) -> None:
        """Set the time between scan sweeps."""
        self.write("TRIG:SOURCE TIMER")
        self.write(f"TRIG:TIMER {seconds:.3f}")
        logger.info("Scan interval set to %.3f s", seconds)

    def set_channel_delay(self, channel: int, delay: float) -> None:
        cl = self._chan_list([channel])
        self.write(f"ROUT:CHAN:DELAY {delay:.3f},{cl}")
        logger.info("Channel %d delay set to %.3f s", channel, delay)

    def enable_channel_in_readings(self) -> None:
        """Enable FORM:READ:CHAN ON so DATA:REM? returns value/channel pairs."""
        self.write("FORM:READ:CHAN ON")

    def initiate_scan(self) -> None:
        """Start the scan (uses _raw_write to avoid blocking on *OPC?)."""
        self._raw_write("INIT")
        logger.info("Scan initiated")

    def abort_scan(self) -> None:
        self._raw_write("ABOR")
        time.sleep(0.5)
        if self._ser:
            self._ser.reset_input_buffer()
        logger.info("Scan aborted")

    def get_data_count(self) -> int:
        """Return the number of readings in instrument memory."""
        try:
            return int(float(self.query("DATA:POIN?")))
        except (ValueError, TypeError):
            return 0

    def fetch_data(self, max_count: Optional[int] = None) -> list[float]:
        """Remove and return readings from instrument memory."""
        count = self.get_data_count()
        if count == 0:
            return []
        if max_count and count > max_count:
            count = max_count
        return self.query_values(f"DATA:REM? {count}")

    # ------------------------------------------------------------------
    # Query helpers (used by backup.py)
    # ------------------------------------------------------------------

    def get_scan_channel_list(self) -> str:
        return self.query("ROUT:SCAN?")

    def query_channel_function(self, channel: int) -> str:
        return self.query(f"SENS:FUNC? {self._chan_list([channel])}").strip()

    def query_channel_range(self, channel: int, scpi_func: str) -> str:
        return self.query(f"{scpi_func}:RANG? {self._chan_list([channel])}").strip()

    def query_channel_nplc(self, channel: int, scpi_func: str) -> str:
        return self.query(f"{scpi_func}:NPLC? {self._chan_list([channel])}").strip()

    def query_tc_type(self, channel: int) -> str:
        return self.query(f"TEMP:TRAN:TC:TYPE? {self._chan_list([channel])}").strip()

    def query_tc_rjunction(self, channel: int) -> str:
        """Returns 'INT', 'FIX', or 'EXT'."""
        return self.query(f"TEMP:TRAN:TC:RJUN:TYPE? {self._chan_list([channel])}").strip()

    def query_channel_delay(self, channel: int) -> str:
        return self.query(f"ROUT:CHAN:DELAY? {self._chan_list([channel])}").strip()

    def query_tc_fixed_rjunction_temp(self, channel: int) -> str:
        return self.query(f"TEMP:TRAN:TC:RJUN:FIX? {self._chan_list([channel])}").strip()

    def query_ac_bandwidth(self, channel: int, scpi_func: str) -> str:
        return self.query(f"{scpi_func}:BAND? {self._chan_list([channel])}").strip()

    def query_trigger_source(self) -> str:
        return self.query("TRIG:SOURCE?").strip()

    def query_trigger_timer(self) -> str:
        return self.query("TRIG:TIMER?").strip()

    def query_trigger_count(self) -> str:
        """Returns '+9.90000000E+37' for infinite scans."""
        return self.query("TRIG:COUNT?").strip()
