"""Download the current instrument configuration to a JSON file."""

from __future__ import annotations

import logging
import re

from .config import (
    AC_FUNCTIONS,
    ChannelConfig,
    ScanConfig,
    NPLC_FUNCTIONS,
    RANGED_FUNCTIONS,
    TC_FUNCTIONS,
)
from .instrument import (
    HP34970A,
    FUNC_MAP,
    normalize_range,
    _RJUN_SCPI_TO_KEY,
)

logger = logging.getLogger(__name__)

# Build a reverse map: every plausible SCPI variant -> canonical key.
# The 34970A returns short quoted forms like '"VOLT"', '"TEMP"', '"RES"'.
_REVERSE_FUNC: dict[str, str] = {}
for _key, _scpi in FUNC_MAP.items():
    upper = _scpi.upper()
    _REVERSE_FUNC[upper] = _key
    _REVERSE_FUNC[upper.split(":")[0]] = _key
    _REVERSE_FUNC[_scpi.lower()] = _key
    _REVERSE_FUNC[_scpi.lower().split(":")[0]] = _key

# Prefer DC variants for bare "VOLT"/"CURR" — AC is disambiguated by range query.
_REVERSE_FUNC["VOLT"] = "dc_voltage"
_REVERSE_FUNC["CURR"] = "dc_current"


def _normalize_func(raw_func: str) -> str:
    """Convert the SCPI function string (e.g. '"VOLT"') to a canonical key (e.g. 'dc_voltage')."""
    cleaned = raw_func.strip().strip('"').upper()
    if cleaned in _REVERSE_FUNC:
        return _REVERSE_FUNC[cleaned]
    # Partial / prefix match as fallback
    for scpi_key, func_key in _REVERSE_FUNC.items():
        if cleaned.startswith(scpi_key):
            return func_key
    logger.warning("Unknown SCPI function '%s' – returning as-is", cleaned)
    return cleaned.lower()


def _scpi_subsystem(func_key: str) -> str:
    return FUNC_MAP.get(func_key, func_key.upper())


def _parse_scan_list(raw: str) -> list[int]:
    """Parse ROUT:SCAN? response into a list of channel ints.

    Handles both comma-separated and range notation: (@101,102,201:210).
    """
    m = re.search(r"@([\d,:]+)", raw)
    if not m:
        return []
    body = m.group(1)
    channels: list[int] = []
    for part in body.split(","):
        if ":" in part:
            lo, hi = part.split(":", 1)
            channels.extend(range(int(lo), int(hi) + 1))
        else:
            channels.append(int(part))
    return channels


_INFINITY_THRESHOLD = 9.0e37   # 34970A returns +9.9E+37 for INF


def _read_scan_interval(inst: HP34970A) -> float:
    try:
        if "TIM" in inst.query_trigger_source().upper():
            val = float(inst.query_trigger_timer())
            if val > 0:
                return round(val, 3)
    except Exception:
        logger.debug("Could not read trigger timer", exc_info=True)
    return 10.0


def _read_scan_count(inst: HP34970A) -> int:
    """Returns 0 for infinite scans."""
    try:
        val = float(inst.query_trigger_count())
        return 0 if val >= _INFINITY_THRESHOLD else max(0, int(val))
    except Exception:
        logger.debug("Could not read trigger count", exc_info=True)
    return 0


def _read_channel(inst: HP34970A, ch_num: int) -> ChannelConfig:
    """Read the complete configuration for a single channel."""
    raw_func = inst.query_channel_function(ch_num)
    func_key = _normalize_func(raw_func)
    scpi_sub = _scpi_subsystem(func_key)

    rng = "auto"
    if func_key in RANGED_FUNCTIONS:
        try:
            rng = normalize_range(inst.query_channel_range(ch_num, scpi_sub))
        except Exception:
            logger.debug("Could not read range for ch %d", ch_num, exc_info=True)

    nplc = 1.0
    if func_key in NPLC_FUNCTIONS:
        try:
            nplc = float(inst.query_channel_nplc(ch_num, scpi_sub))
        except Exception:
            logger.debug("Could not read NPLC for ch %d", ch_num, exc_info=True)

    tc_type = "K"
    ref_junction = "internal"
    ref_fixed_temp = None
    if func_key in TC_FUNCTIONS:
        try:
            tc_type = inst.query_tc_type(ch_num).strip().upper()
        except Exception:
            logger.debug("Could not read TC type for ch %d", ch_num, exc_info=True)
        try:
            ref_junction = _RJUN_SCPI_TO_KEY.get(inst.query_tc_rjunction(ch_num).strip().upper(), "internal")
        except Exception:
            logger.debug("Could not read ref junction for ch %d", ch_num, exc_info=True)
        if ref_junction == "fixed":
            try:
                ref_fixed_temp = float(inst.query_tc_fixed_rjunction_temp(ch_num))
            except Exception:
                logger.debug("Could not read fixed ref junction temp for ch %d", ch_num, exc_info=True)

    ac_bandwidth = None
    if func_key in AC_FUNCTIONS:
        try:
            ac_bandwidth = float(inst.query_ac_bandwidth(ch_num, scpi_sub))
        except Exception:
            logger.debug("Could not read AC bandwidth for ch %d", ch_num, exc_info=True)

    delay = None
    try:
        delay_val = float(inst.query_channel_delay(ch_num))
        if delay_val > 0:
            delay = delay_val
    except Exception:
        logger.debug("Could not read channel delay for ch %d", ch_num, exc_info=True)

    cc = ChannelConfig(
        channel=ch_num,
        name=f"ch{ch_num}",
        function=func_key,
        range=rng,
        nplc=nplc,
        tc_type=tc_type,
        ref_junction=ref_junction,
        ref_fixed_temp=ref_fixed_temp,
        ac_bandwidth=ac_bandwidth,
        delay=delay,
        unit="",
        gain=1.0,
        offset=0.0,
    )
    logger.info(
        "Read ch %d: func=%s range=%s nplc=%.1f tc=%s rj=%s delay=%s",
        ch_num, func_key, rng, nplc, tc_type, ref_junction, delay,
    )
    return cc


def download_config(
    inst: HP34970A,
    output_path: str = "backup.json",
    description: str = "Backup from instrument",
) -> ScanConfig:
    """Read the full scan config from the 34970A and save to JSON.

    Output uses the same schema as a hand-authored scan file (myscan.json).
    """
    scan_channels = _parse_scan_list(inst.get_scan_channel_list())
    if not scan_channels:
        logger.warning("No scan list configured on instrument")

    scan_cfg = ScanConfig(
        channels=[_read_channel(inst, ch) for ch in scan_channels],
        scan_interval=_read_scan_interval(inst),
        scan_count=_read_scan_count(inst),
        description=description,
    )
    scan_cfg.save(output_path)
    return scan_cfg
