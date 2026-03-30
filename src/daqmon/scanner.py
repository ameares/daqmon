"""Core scanning engine – configures the 34970A and runs the scan loop."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

from .config import ChannelConfig, ScanConfig
from .csv_writer import CsvWriter
from .influx import InfluxWriter
from .instrument import HP34970A

logger = logging.getLogger(__name__)


def configure_channel(inst: HP34970A, ch: ChannelConfig) -> None:
    """Apply a single channel's measurement configuration to the instrument."""
    chans = [ch.channel]
    func = ch.function.lower()

    if func == "dc_voltage":
        inst.configure_dc_voltage(chans, range_val=ch.range, nplc=ch.nplc)
    elif func == "ac_voltage":
        inst.configure_ac_voltage(chans, range_val=ch.range, ac_bandwidth=ch.ac_bandwidth)
    elif func == "dc_current":
        inst.configure_dc_current(chans, range_val=ch.range, nplc=ch.nplc)
    elif func == "ac_current":
        inst.configure_ac_current(chans, range_val=ch.range, ac_bandwidth=ch.ac_bandwidth)
    elif func == "resistance_2w":
        inst.configure_resistance_2w(chans, range_val=ch.range, nplc=ch.nplc)
    elif func == "resistance_4w":
        inst.configure_resistance_4w(chans, range_val=ch.range, nplc=ch.nplc)
    elif func == "frequency":
        inst.configure_frequency(chans, range_val=ch.range)
    elif func == "period":
        inst.configure_period(chans, range_val=ch.range)
    elif func in ("temperature", "thermocouple"):
        inst.configure_thermocouple(
            chans,
            tc_type=ch.tc_type,
            ref_junction=ch.ref_junction,
            ref_channel=ch.ref_channel,
            ref_fixed_temp=ch.ref_fixed_temp,
            nplc=ch.nplc,
        )
    elif func == "digital_input":
        inst.configure_digital_input(chans)
    elif func == "totalize":
        inst.configure_totalizer(chans)
    else:
        logger.warning("Unknown function '%s' for channel %d – skipping", func, ch.channel)
        return
    
    # Apply per-channel relay delay if specified
    if ch.delay is not None:
        inst.set_channel_delay(ch.channel, ch.delay)

    logger.info(
        "Configured ch %d (%s) as %s range=%s nplc=%.1f",
        ch.channel, ch.name, func, ch.range, ch.nplc,
    )


def configure_scan(inst: HP34970A, scan_cfg: ScanConfig) -> None:
    """Apply full scan configuration to the instrument."""
    inst.reset()
    inst.clear_status()
    time.sleep(0.5)

    for ch in scan_cfg.channels:
        configure_channel(inst, ch)

    inst.set_scan_list(scan_cfg.channel_numbers)
    inst.set_scan_interval(scan_cfg.scan_interval)
    inst.set_scan_count(scan_cfg.scan_count)
    inst.enable_channel_in_readings()

    logger.info(
        "Scan configured: %d channels, interval=%.1fs, count=%s",
        len(scan_cfg.channels),
        scan_cfg.scan_interval,
        "infinite" if scan_cfg.scan_count <= 0 else scan_cfg.scan_count,
    )


def parse_readings(
    raw: list[tuple[float, int]],
    scan_cfg: ScanConfig,
) -> list[dict[str, Any]]:
    """Map (value, channel) pairs to named readings; append _rise channels if ambient_correction is set."""
    readings: list[dict[str, Any]] = []
    n_channels = len(scan_cfg.channels)
    if n_channels == 0:
        return readings

    ch_by_num: dict[int, ChannelConfig] = {ch.channel: ch for ch in scan_cfg.channels}
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
    inst: HP34970A,
    scan_cfg: ScanConfig,
    influx: InfluxWriter,
    csv_writer: CsvWriter | None = None,
    poll_interval: float = 2.0,
    stop_event=None,
) -> None:
    """Run the scan loop, fetching data and writing to InfluxDB and CSV."""
    configure_scan(inst, scan_cfg)
    inst.initiate_scan()
    logger.info("Scan running – press Ctrl-C to stop")

    sweep_count = 0
    n_channels = len(scan_cfg.channels)
    total_readings = 0

    try:
        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received")
                break

            time.sleep(poll_interval)

            available = inst.get_data_count()
            if available < n_channels:
                continue

            n_complete_sweeps = available // n_channels
            if n_complete_sweeps > 1:
                logger.warning(
                    "Data loss: %d sweeps accumulated (expected 1); discarding all but the latest",
                    n_complete_sweeps,
                )
            raw = inst.query_readings_with_channels(f"DATA:REM? {n_complete_sweeps * n_channels}")
            if not raw:
                continue
            raw = raw[-n_channels:]

            readings = parse_readings(raw, scan_cfg)
            sweep_count += 1
            total_readings += len(raw)

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
            inst.abort_scan()
        except Exception:
            pass
        logger.info("Scan loop ended (total sweeps: %d)", sweep_count)
