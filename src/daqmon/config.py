"""Scan configuration data model and JSON loader/saver."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Functions that support range configuration
RANGED_FUNCTIONS = {
    "dc_voltage", "ac_voltage",
    "dc_current", "ac_current",
    "resistance_2w", "resistance_4w",
    "frequency", "period",
}

# Functions that support AC bandwidth filter
AC_FUNCTIONS = {"ac_voltage", "ac_current"}

# Functions that support NPLC configuration
NPLC_FUNCTIONS = {
    "dc_voltage", "dc_current",
    "resistance_2w", "resistance_4w",
    "temperature",
}

# Functions that are thermocouple-based
TC_FUNCTIONS = {"temperature", "thermocouple"}


@dataclass
class ChannelConfig:
    """Configuration for a single measurement channel."""

    channel: int
    name: str
    function: str = "dc_voltage"
    range: str = "auto"
    nplc: float = 1.0
    tc_type: str = "K"
    ref_junction: str = "internal"
    ref_channel: Optional[int] = None
    unit: str = ""
    gain: float = 1.0
    offset: float = 0.0
    delay: Optional[float] = None
    ac_bandwidth: Optional[float] = None
    ref_fixed_temp: Optional[float] = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict, only including fields relevant to the function."""
        func = self.function.lower()
        d: dict[str, Any] = {
            "channel": self.channel,
            "name": self.name,
            "function": self.function,
        }
        if func in RANGED_FUNCTIONS:
            d["range"] = self.range
        if func in NPLC_FUNCTIONS:
            d["nplc"] = self.nplc
        if func in TC_FUNCTIONS:
            d["tc_type"] = self.tc_type
            d["ref_junction"] = self.ref_junction
            if self.ref_junction == "external" and self.ref_channel is not None:
                d["ref_channel"] = self.ref_channel
            if self.ref_junction == "fixed" and self.ref_fixed_temp is not None:
                d["ref_fixed_temp"] = self.ref_fixed_temp
        if func in AC_FUNCTIONS and self.ac_bandwidth is not None:
            d["ac_bandwidth"] = self.ac_bandwidth
        if self.unit:
            d["unit"] = self.unit
        d["gain"] = self.gain
        d["offset"] = self.offset
        if self.delay is not None:
            d["delay"] = self.delay
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ChannelConfig":
        return cls(
            channel=int(d["channel"]),
            name=str(d.get("name", f"ch{d['channel']}")),
            function=str(d.get("function", "dc_voltage")),
            range=str(d.get("range", "auto")),
            nplc=float(d.get("nplc", 1.0)),
            tc_type=str(d.get("tc_type", "K")),
            ref_junction=str(d.get("ref_junction", "internal")),
            ref_channel=d.get("ref_channel"),
            unit=str(d.get("unit", "")),
            gain=float(d.get("gain", 1.0)),
            offset=float(d.get("offset", 0.0)),
            delay=float(d["delay"]) if "delay" in d else None,
            ac_bandwidth=float(d["ac_bandwidth"]) if "ac_bandwidth" in d else None,
            ref_fixed_temp=float(d["ref_fixed_temp"]) if "ref_fixed_temp" in d else None,
            extra=dict(d.get("extra", {})),
        )


@dataclass
class ScanConfig:
    """Full scan definition that can be serialized to / from JSON."""

    channels: list[ChannelConfig] = field(default_factory=list)
    scan_interval: float = 10.0          # seconds between sweeps
    scan_count: int = 0                  # 0 = infinite / continuous
    description: str = ""                # optional description
    ambient_correction: bool = False     # if True, compute _rise channels
    ambient_channel: Optional[int] = None  # channel number used as ambient reference
    instrument_type: str = "hp34970a"   # selects the instrument driver

    @property
    def channel_numbers(self) -> list[int]:
        return [ch.channel for ch in self.channels]

    @property
    def channel_name_map(self) -> dict[int, str]:
        return {ch.channel: ch.name for ch in self.channels}

    @property
    def temperature_channels(self) -> list[ChannelConfig]:
        """Return all temperature channels excluding the ambient channel."""
        return [
            ch for ch in self.channels
            if ch.function.lower() in TC_FUNCTIONS
            and ch.channel != self.ambient_channel
        ]

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "instrument_type": self.instrument_type,
            "description": self.description,
            "scan_interval": self.scan_interval,
            "scan_count": self.scan_count,
        }
        if self.ambient_correction:
            d["ambient_correction"] = self.ambient_correction
            d["ambient_channel"] = self.ambient_channel
        d["channels"] = [ch.to_dict() for ch in self.channels]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ScanConfig":
        channels = [ChannelConfig.from_dict(c) for c in d.get("channels", [])]
        ambient_correction = bool(d.get("ambient_correction", False))
        ambient_channel = d.get("ambient_channel", None)
        if ambient_correction and ambient_channel is None:
            logger.warning(
                "ambient_correction is enabled but ambient_channel is not set – "
                "correction will be skipped"
            )
        return cls(
            channels=channels,
            scan_interval=float(d.get("scan_interval", 10.0)),
            scan_count=int(d.get("scan_count", 0)),
            description=str(d.get("description", "")),
            ambient_correction=ambient_correction,
            ambient_channel=int(ambient_channel) if ambient_channel is not None else None,
            instrument_type=str(d.get("instrument_type", "hp34970a")),
        )

    def save(self, path: str | Path) -> None:
        p = Path(path)
        with p.open("w") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Scan config saved to %s", p)

    @classmethod
    def load(cls, path: str | Path) -> "ScanConfig":
        p = Path(path)
        with p.open() as f:
            data = json.load(f)
        logger.info("Scan config loaded from %s", p)
        return cls.from_dict(data)
