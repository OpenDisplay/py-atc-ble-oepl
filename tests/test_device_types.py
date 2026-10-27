"""Tests for device type name lookup and color scheme mapping."""

import pytest

from py_atc_ble_oepl.models.device_types import (
    DEVICE_TYPES,
    SCREEN_TYPE_COLOR_SCHEME,
    get_device_type_name,
    guess_manufacturer,
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


class TestGuessManufacturer:
    @pytest.mark.parametrize(
        ("screen_type", "maker"),
        [
            (5, "Hanshow"),  # 200 HS BWY SSD, seen on a real HS 2.00" BWY
            (16, "Hanshow"),  # 213 HS BWR SSD, a Hanshow Stellar Pro 213
            (12, "Gicisky"),  # 290 Gici BWR SSD
            (15, "SoluM"),  # 1200 TI BWR, an M3 12.2"
            (26, "SoluM"),  # 581 TI BW
        ],
    )
    def test_maker_from_the_code_in_the_name(self, screen_type: int, maker: str):
        assert guess_manufacturer(screen_type) == maker

    @pytest.mark.parametrize("screen_type", [36, 41, 65535, 9999])
    def test_no_guess_without_a_known_maker_code(self, screen_type: int):
        # 36 and 41 are WO types, whose maker is not known.
        assert guess_manufacturer(screen_type) is None

    def test_only_the_wo_types_and_the_dynamic_type_have_no_maker(self):
        unknown = {name for t, name in DEVICE_TYPES.items() if guess_manufacturer(t) is None}
        assert unknown == {"Dynamic (HW Config Tab)", "290 WO BWRY JD", "290 WO BWRY JD V2", "260 WO BWRY JD V2"}
