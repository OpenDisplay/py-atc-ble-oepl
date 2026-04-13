"""Tests for device type name lookup and color scheme mapping."""

import pytest

from py_atc_ble_oepl.models.device_types import (
    DEVICE_TYPES,
    SCREEN_TYPE_COLOR_SCHEME,
    get_device_type_name,
)


class TestGetDeviceTypeName:
    def test_known_type_returns_name(self):
        assert get_device_type_name(7) == "350 HS BWR UC"

    def test_special_dynamic_type(self):
        assert get_device_type_name(65535) == "Dynamic (HW Config Tab)"

    def test_unknown_type_returns_hex_string(self):
        assert get_device_type_name(9999) == "unknown (0x270F)"

    def test_zero_type_returns_unknown(self):
        result = get_device_type_name(0)
        assert result.startswith("unknown")

    def test_all_known_types_return_nonempty_string(self):
        for screen_type in DEVICE_TYPES:
            name = get_device_type_name(screen_type)
            assert isinstance(name, str) and len(name) > 0

    @pytest.mark.parametrize(
        "screen_type,expected_name",
        [
            (1, "350 HS BWY UC"),
            (4, "350 HS BW UC"),
            (10, "213 HS BW UC"),
            (17, "350 HS BWRY JD"),
            (47, "213 HS BWR UC V2"),
        ],
    )
    def test_spot_check_device_names(self, screen_type: int, expected_name: str):
        assert get_device_type_name(screen_type) == expected_name


class TestScreenTypeColorScheme:
    def test_bwy_type(self):
        assert SCREEN_TYPE_COLOR_SCHEME[1] == 2  # BWY

    def test_mono_type(self):
        assert SCREEN_TYPE_COLOR_SCHEME[4] == 0  # MONO

    def test_bwr_type(self):
        assert SCREEN_TYPE_COLOR_SCHEME[7] == 1  # BWR

    def test_bwry_type(self):
        assert SCREEN_TYPE_COLOR_SCHEME[17] == 3  # BWRY

    def test_all_values_in_valid_range(self):
        for screen_type, color_scheme in SCREEN_TYPE_COLOR_SCHEME.items():
            assert color_scheme in (0, 1, 2, 3), f"screen_type {screen_type} has invalid color_scheme {color_scheme}"

    def test_all_screen_types_1_to_47_present(self):
        for i in range(1, 48):
            assert i in SCREEN_TYPE_COLOR_SCHEME, f"screen_type {i} missing from SCREEN_TYPE_COLOR_SCHEME"
