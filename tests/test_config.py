"""Tests for config.py dataclasses and serialization."""

import json
import pytest
from daqmon.config import ChannelConfig, ScanConfig


def test_channel_config_defaults():
    ch = ChannelConfig(channel=101, name="temp1")
    assert ch.function == "dc_voltage"
    assert ch.gain == 1.0
    assert ch.offset == 0.0
    assert ch.delay is None


def test_channel_config_round_trip():
    ch = ChannelConfig(channel=102, name="v_bus", function="dc_voltage", range="10", nplc=2.0, gain=2.0, offset=0.5)
    d = ch.to_dict()
    ch2 = ChannelConfig.from_dict(d)
    assert ch2.channel == ch.channel
    assert ch2.name == ch.name
    assert ch2.function == ch.function
    assert ch2.range == ch.range
    assert ch2.nplc == ch.nplc
    assert ch2.gain == ch.gain
    assert ch2.offset == ch.offset


def test_channel_config_tc_round_trip():
    ch = ChannelConfig(channel=103, name="tc1", function="temperature", tc_type="K", ref_junction="internal")
    d = ch.to_dict()
    assert "tc_type" in d
    assert "ref_junction" in d
    # ranged fields should not appear for thermocouple
    assert "range" not in d
    ch2 = ChannelConfig.from_dict(d)
    assert ch2.tc_type == "K"
    assert ch2.ref_junction == "internal"


def test_channel_config_omits_irrelevant_fields():
    ch = ChannelConfig(channel=104, name="freq1", function="frequency", range="auto")
    d = ch.to_dict()
    assert "nplc" not in d
    assert "tc_type" not in d


def test_scan_config_defaults():
    sc = ScanConfig()
    assert sc.scan_interval == 10.0
    assert sc.scan_count == 0
    assert sc.channels == []


def test_scan_config_round_trip():
    ch = ChannelConfig(channel=101, name="v1", function="dc_voltage")
    sc = ScanConfig(channels=[ch], scan_interval=5.0, scan_count=3, description="test scan")
    d = sc.to_dict()
    sc2 = ScanConfig.from_dict(d)
    assert sc2.scan_interval == 5.0
    assert sc2.scan_count == 3
    assert sc2.description == "test scan"
    assert len(sc2.channels) == 1
    assert sc2.channels[0].name == "v1"


def test_scan_config_channel_numbers():
    sc = ScanConfig(channels=[
        ChannelConfig(channel=101, name="a"),
        ChannelConfig(channel=102, name="b"),
    ])
    assert sc.channel_numbers == [101, 102]


def test_scan_config_channel_name_map():
    sc = ScanConfig(channels=[
        ChannelConfig(channel=101, name="alpha"),
        ChannelConfig(channel=102, name="beta"),
    ])
    assert sc.channel_name_map == {101: "alpha", 102: "beta"}


def test_scan_config_save_load(tmp_path):
    ch = ChannelConfig(channel=101, name="v1", function="dc_voltage", gain=1.5)
    sc = ScanConfig(channels=[ch], scan_interval=2.0)
    path = tmp_path / "scan.json"
    sc.save(path)
    sc2 = ScanConfig.load(path)
    assert sc2.scan_interval == 2.0
    assert sc2.channels[0].gain == 1.5


def test_scan_config_temperature_channels_excludes_ambient():
    sc = ScanConfig(
        channels=[
            ChannelConfig(channel=101, name="ambient", function="temperature"),
            ChannelConfig(channel=102, name="tc1", function="temperature"),
        ],
        ambient_correction=True,
        ambient_channel=101,
    )
    temp_chs = sc.temperature_channels
    assert len(temp_chs) == 1
    assert temp_chs[0].channel == 102
