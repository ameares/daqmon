"""Core scanning engine – instrument-agnostic scan loop."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from .config import ScanConfig
from .csv_writer import CsvWriter
from .influx import InfluxWriter
from .instruments.base import InstrumentBase

logger = logging.getLogger(__name__)


def parse_readings(
    raw: list[tuple[float, int]],
    scan_cfg: ScanConfig,
) -> list[dict[str, Any]]:
    """Map (value, channel) pairs to named readings; append _rise channels if ambient_correction is set."""
    readings: list[dict[str, Any]] = []
    n_channels = len(scan_cfg.channels)
    if n_channels == 0:
        return readings

    ch_by_num = {ch.channel: ch for ch in scan_cfg.channels}
    now = datetime.now(timezone.utc)

    n_sweeps = len(raw) // n_channels

    for sweep_idx in range(n_sweeps):
        sweep_slice = raw[sweep_idx * n_channels : (sweep_idx + 1) * n_channels]

        sweep_readings: list[dict[str, Any]] = []
        sweep_values_by_channel: dict[int, float] = {}

        for value, ch_num in sweep_slice:
            ch = ch_by_num.get(ch_num)
            if ch is None:
                logger.warning("Reading for unknown channel %d – skipping", ch_num)
                continue
            scaled = value * ch.gain + ch.offset
            sweep_readings.append({
                "channel": ch.channel,
                "name": ch.name,
                "value": scaled,
                "unit": ch.unit,
                "timestamp": now,
            })
            sweep_values_by_channel[ch.channel] = scaled

        readings.extend(sweep_readings)

        if (
            scan_cfg.ambient_correction
            and scan_cfg.ambient_channel is not None
            and scan_cfg.ambient_channel in sweep_values_by_channel
        ):
            ambient_val = sweep_values_by_channel[scan_cfg.ambient_channel]
            for ch in scan_cfg.temperature_channels:
                ch_val = sweep_values_by_channel.get(ch.channel)
                if ch_val is None:
                    continue
                readings.append({
                    "channel": ch.channel,
                    "name": f"{ch.name}_rise",
                    "value": ch_val - ambient_val,
                    "unit": ch.unit,
                    "timestamp": now,
                })

    return readings


def run_scan(
    inst: InstrumentBase,
    scan_cfg: ScanConfig,
    influx: InfluxWriter,
    csv_writer: CsvWriter | None = None,
    poll_interval: float = 2.0,
    stop_event=None,
) -> None:
    """Configure *inst*, then run the scan loop until stopped.

    The loop calls :meth:`~InstrumentBase.fetch_sweep` every *poll_interval*
    seconds.  Each instrument controls its own timing: hardware-timed devices
    return ``None`` until their buffer holds a complete sweep; software-timed
    devices (Fluke 45, RandomInstrument) enforce ``scan_interval`` internally
    and measure on demand.
    """
    inst.configure(scan_cfg)
    inst.start()
    logger.info("Scan running – press Ctrl-C to stop")

    sweep_count = 0
    total_readings = 0

    try:
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received")
                break

            time.sleep(poll_interval)

            sweep = inst.fetch_sweep()
            if sweep is None:
                continue

            readings = parse_readings(sweep, scan_cfg)
            sweep_count += 1
            total_readings += len(sweep)

            for r in readings:
                logger.info(
                    "DATA  ch=%d  name=%-20s  value=%+14.6e  unit=%s",
                    r["channel"], r["name"], r["value"], r.get("unit", ""),
                )

            influx.write_readings(readings)
            if csv_writer:
                try:
                    csv_writer.write_readings(readings)
                except Exception:
                    logger.exception("Failed to write to CSV log")

            logger.info(
                "Sweep %d | %d new values (%d total readings)",
                sweep_count, len(readings), total_readings,
            )

            if scan_cfg.scan_count > 0 and sweep_count >= scan_cfg.scan_count:
                logger.info("Completed %d scans – stopping", sweep_count)
                break

    except KeyboardInterrupt:
        logger.info("Ctrl-C caught in scan loop")
    finally:
        try:
            inst.stop()
        except Exception:
            pass
        logger.info("Scan loop ended (total sweeps: %d)", sweep_count)
