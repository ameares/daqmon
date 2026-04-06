"""Tests for RandomInstrument and the instrument registry."""

import time

import pytest

from daqmon.config import ChannelConfig, ScanConfig
from daqmon.instruments import RandomInstrument, make_instrument, registered_types
from daqmon.instruments.base import InstrumentBase


def make_random_scan(*channels):
    return ScanConfig(
        instrument_type="random",
        scan_interval=0.05,  # short for fast tests
        channels=list(channels),
    )


def test_random_instrument_is_instrument_base():
    assert issubclass(RandomInstrument, InstrumentBase)


def test_random_instrument_idn():
    inst = RandomInstrument()
    assert "random" in inst.idn().lower()


def test_random_instrument_open_close_noop():
    inst = RandomInstrument()
    inst.open()
    inst.close()


def test_random_instrument_no_sweep_before_start():
    inst = RandomInstrument()
    sc = make_random_scan(ChannelConfig(channel=1, name="a"))
    inst.open()
    inst.configure(sc)
    assert inst.fetch_sweep() is None  # not started yet
    inst.close()


def test_random_instrument_returns_sweep_immediately_after_start():
    inst = RandomInstrument(seed=42)
    sc = make_random_scan(ChannelConfig(channel=1, name="a"))
    inst.open()
    inst.configure(sc)
    inst.start()
    sweep = inst.fetch_sweep()
    assert sweep is not None
    assert len(sweep) == 1
    value, ch_num = sweep[0]
    assert ch_num == 1
    assert isinstance(value, float)
    inst.stop()
    inst.close()


def test_random_instrument_respects_scan_interval():
    inst = RandomInstrument(seed=0)
    sc = make_random_scan(ChannelConfig(channel=1, name="a"))
    inst.open()
    inst.configure(sc)
    inst.start()
    inst.fetch_sweep()  # consume the immediate first sweep

    # Should return None while interval has not elapsed
    assert inst.fetch_sweep() is None

    # After waiting, should produce a sweep
    time.sleep(sc.scan_interval + 0.01)
    sweep = inst.fetch_sweep()
    assert sweep is not None
    inst.stop()
    inst.close()


def test_random_instrument_multi_channel():
    inst = RandomInstrument(seed=7)
    sc = make_random_scan(
        ChannelConfig(channel=1, name="ch1", extra={"mean": 10.0, "std": 0.0}),
        ChannelConfig(channel=2, name="ch2", extra={"mean": 20.0, "std": 0.0}),
        ChannelConfig(channel=3, name="ch3", extra={"mean": 30.0, "std": 0.0}),
    )
    inst.open()
    inst.configure(sc)
    inst.start()
    sweep = inst.fetch_sweep()
    assert sweep is not None
    assert len(sweep) == 3
    values_by_ch = {ch: v for v, ch in sweep}
    assert values_by_ch[1] == pytest.approx(10.0)
    assert values_by_ch[2] == pytest.approx(20.0)
    assert values_by_ch[3] == pytest.approx(30.0)
    inst.stop()
    inst.close()


def test_random_instrument_no_sweep_after_stop():
    inst = RandomInstrument(seed=1)
    sc = make_random_scan(ChannelConfig(channel=1, name="a"))
    inst.open()
    inst.configure(sc)
    inst.start()
    inst.fetch_sweep()  # consume immediate sweep
    inst.stop()
    assert inst.fetch_sweep() is None


def test_registry_contains_all_builtin_instruments():
    types = registered_types()
    assert "hp34970a" in types
    assert "fluke45" in types
    assert "random" in types


def test_registry_make_instrument_random():
    inst = make_instrument("random")
    assert isinstance(inst, RandomInstrument)


def test_registry_make_instrument_unknown():
    with pytest.raises(ValueError, match="Unknown instrument_type"):
        make_instrument("nonexistent_device")


def test_scan_config_instrument_type_defaults_to_hp34970a():
    sc = ScanConfig()
    assert sc.instrument_type == "hp34970a"


def test_scan_config_instrument_type_round_trip():
    sc = ScanConfig(instrument_type="random")
    d = sc.to_dict()
    assert d["instrument_type"] == "random"
    sc2 = ScanConfig.from_dict(d)
    assert sc2.instrument_type == "random"


def test_scan_config_instrument_type_backwards_compat(tmp_path):
    """Configs without instrument_type load as hp34970a."""
    import json
    old_config = {
        "description": "legacy",
        "scan_interval": 5.0,
        "scan_count": 0,
        "channels": [],
    }
    p = tmp_path / "old.json"
    p.write_text(json.dumps(old_config))
    sc = ScanConfig.load(p)
    assert sc.instrument_type == "hp34970a"


def test_channel_extra_round_trip():
    ch = ChannelConfig(channel=1, name="x", extra={"mean": 5.0, "std": 0.1})
    d = ch.to_dict()
    assert "extra" in d
    ch2 = ChannelConfig.from_dict(d)
    assert ch2.extra == {"mean": 5.0, "std": 0.1}


def test_channel_extra_omitted_when_empty():
    ch = ChannelConfig(channel=1, name="x")
    d = ch.to_dict()
    assert "extra" not in d
