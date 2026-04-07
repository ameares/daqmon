"""Tests for Fluke45 driver – pure logic (no hardware)."""

import pytest

from daqmon.config import ChannelConfig, ScanConfig
from daqmon.instruments.fluke45 import FUNC_MAP, Fluke45


def make_fluke_scan(*channels):
    return ScanConfig(
        instrument_type="fluke45",
        scan_interval=1.0,
        channels=list(channels),
    )


def ch(num, func="dc_voltage"):
    return ChannelConfig(channel=num, name=f"ch{num}", function=func)


class TestValidateConfig:
    def test_single_primary_channel(self):
        sc = make_fluke_scan(ch(1))
        primary, secondary = Fluke45._validate_config(sc)
        assert primary.channel == 1
        assert secondary is None

    def test_primary_and_secondary(self):
        sc = make_fluke_scan(ch(1), ch(2, "frequency"))
        primary, secondary = Fluke45._validate_config(sc)
        assert primary.channel == 1
        assert secondary is not None
        assert secondary.channel == 2
        assert secondary.function == "frequency"

    def test_zero_channels_raises(self):
        sc = make_fluke_scan()
        with pytest.raises(ValueError, match="1 or 2"):
            Fluke45._validate_config(sc)

    def test_three_channels_raises(self):
        sc = make_fluke_scan(ch(1), ch(2), ChannelConfig(channel=3, name="x"))
        with pytest.raises(ValueError, match="1 or 2"):
            Fluke45._validate_config(sc)

    def test_wrong_channel_numbers_raises(self):
        sc = make_fluke_scan(ChannelConfig(channel=3, name="x", function="dc_voltage"))
        with pytest.raises(ValueError, match="channel numbers must be 1"):
            Fluke45._validate_config(sc)

    def test_missing_primary_channel_raises(self):
        sc = make_fluke_scan(ch(2))
        with pytest.raises(ValueError, match="channel 1"):
            Fluke45._validate_config(sc)

    def test_unsupported_primary_function_raises(self):
        sc = make_fluke_scan(ChannelConfig(channel=1, name="t", function="temperature"))
        with pytest.raises(ValueError, match="primary"):
            Fluke45._validate_config(sc)

    def test_unsupported_secondary_function_raises(self):
        sc = make_fluke_scan(ch(1), ChannelConfig(channel=2, name="t", function="temperature"))
        with pytest.raises(ValueError, match="secondary"):
            Fluke45._validate_config(sc)

    def test_all_supported_functions_accepted_on_primary(self):
        for func in FUNC_MAP:
            sc = make_fluke_scan(ChannelConfig(channel=1, name="x", function=func))
            primary, _ = Fluke45._validate_config(sc)
            assert primary.function == func

    def test_all_supported_functions_accepted_on_secondary(self):
        for func in FUNC_MAP:
            sc = make_fluke_scan(ch(1), ChannelConfig(channel=2, name="x", function=func))
            _, secondary = Fluke45._validate_config(sc)
            assert secondary is not None
            assert secondary.function == func


class TestParseDualResponse:
    def test_parses_valid_response(self):
        result = Fluke45._parse_dual_response("+1.2345E+0,+6.7890E+3")
        assert result == pytest.approx((1.2345, 6789.0))

    def test_parses_negative_values(self):
        result = Fluke45._parse_dual_response("-1.0E+0,-2.5E+1")
        assert result == pytest.approx((-1.0, -25.0))

    def test_strips_whitespace(self):
        result = Fluke45._parse_dual_response("  +1.0E+0,+2.0E+0  ")
        assert result == pytest.approx((1.0, 2.0))

    def test_returns_none_for_single_value(self):
        assert Fluke45._parse_dual_response("+1.0E+0") is None

    def test_returns_none_for_three_values(self):
        assert Fluke45._parse_dual_response("+1.0E+0,+2.0E+0,+3.0E+0") is None

    def test_returns_none_for_non_numeric_first(self):
        assert Fluke45._parse_dual_response("OL,+1.0E+0") is None

    def test_returns_none_for_non_numeric_second(self):
        assert Fluke45._parse_dual_response("+1.0E+0,OL") is None

    def test_returns_none_for_empty(self):
        assert Fluke45._parse_dual_response("") is None
