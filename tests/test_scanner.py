"""Tests for scanner.py – pure logic (no hardware)."""

import pytest
from daqmon.config import ChannelConfig, ScanConfig
from daqmon.scanner import parse_readings


def make_scan(*channels):
    return ScanConfig(channels=list(channels))


def test_parse_readings_empty_raw():
    sc = make_scan(ChannelConfig(channel=101, name="v1"))
    assert parse_readings([], sc) == []


def test_parse_readings_empty_channels():
    assert parse_readings([(1.0, 101)], ScanConfig()) == []


def test_parse_readings_basic():
    sc = make_scan(ChannelConfig(channel=101, name="v_bus", unit="V"))
    readings = parse_readings([(3.3, 101)], sc)
    assert len(readings) == 1
    r = readings[0]
    assert r["channel"] == 101
    assert r["name"] == "v_bus"
    assert r["value"] == pytest.approx(3.3)
    assert r["unit"] == "V"


def test_parse_readings_gain_offset():
    sc = make_scan(ChannelConfig(channel=101, name="scaled", gain=2.0, offset=1.0))
    readings = parse_readings([(5.0, 101)], sc)
    # value = 5.0 * 2.0 + 1.0
    assert readings[0]["value"] == pytest.approx(11.0)


def test_parse_readings_multiple_channels():
    sc = make_scan(
        ChannelConfig(channel=101, name="ch1"),
        ChannelConfig(channel=102, name="ch2"),
    )
    raw = [(1.0, 101), (2.0, 102)]
    readings = parse_readings(raw, sc)
    assert len(readings) == 2
    names = {r["name"] for r in readings}
    assert names == {"ch1", "ch2"}


def test_parse_readings_unknown_channel_skipped():
    sc = make_scan(ChannelConfig(channel=101, name="v1"))
    readings = parse_readings([(9.9, 999)], sc)
    assert readings == []


def test_parse_readings_ambient_correction():
    sc = ScanConfig(
        channels=[
            ChannelConfig(channel=101, name="ambient", function="temperature"),
            ChannelConfig(channel=102, name="tc1", function="temperature"),
        ],
        ambient_correction=True,
        ambient_channel=101,
    )
    raw = [(25.0, 101), (75.0, 102)]
    readings = parse_readings(raw, sc)
    names = {r["name"]: r["value"] for r in readings}
    assert "ambient" in names
    assert "tc1" in names
    assert "tc1_rise" in names
    assert names["tc1_rise"] == pytest.approx(50.0)


def test_parse_readings_no_ambient_correction_when_disabled():
    sc = ScanConfig(
        channels=[
            ChannelConfig(channel=101, name="ambient", function="temperature"),
            ChannelConfig(channel=102, name="tc1", function="temperature"),
        ],
        ambient_correction=False,
        ambient_channel=101,
    )
    readings = parse_readings([(25.0, 101), (75.0, 102)], sc)
    names = {r["name"] for r in readings}
    assert "tc1_rise" not in names
