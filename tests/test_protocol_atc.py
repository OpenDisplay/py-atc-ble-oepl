"""Tests for ATCProtocol: battery calculation, advertising parsing, and device interrogation."""

import struct

import pytest
from conftest import build_display_info_response, build_dynamic_config_response

from py_atc_ble_oepl.exceptions import BLEProtocolError
from py_atc_ble_oepl.protocol.atc import ATCProtocol


@pytest.fixture
def protocol() -> ATCProtocol:
    return ATCProtocol()


class TestCalculateBatteryPercentage:
    def test_zero_voltage_returns_zero(self):
        assert ATCProtocol._calculate_battery_percentage(0) == 0

    def test_min_voltage_returns_zero(self):
        assert ATCProtocol._calculate_battery_percentage(2600) == 0

    def test_max_voltage_returns_100(self):
        assert ATCProtocol._calculate_battery_percentage(3200) == 100

    def test_higher_voltage_gives_higher_percentage(self):
        low = ATCProtocol._calculate_battery_percentage(2700)
        high = ATCProtocol._calculate_battery_percentage(3000)
        assert low < high

    def test_above_max_clamps_to_100(self):
        assert ATCProtocol._calculate_battery_percentage(4200) == 100

    def test_below_min_clamps_to_zero(self):
        assert ATCProtocol._calculate_battery_percentage(1000) == 0

    def test_result_always_in_range(self):
        for mv in range(0, 5000, 100):
            pct = ATCProtocol._calculate_battery_percentage(mv)
            assert 0 <= pct <= 100


class TestParseAdvertisingData:
    def _v1(
        self,
        hw_type: int = 0x0042,
        fw_version: int = 0x0100,
        battery_mv: int = 3000,
    ) -> bytes:
        buf = bytearray(10)
        buf[0] = 1
        buf[1:3] = hw_type.to_bytes(2, "little")
        buf[3:5] = fw_version.to_bytes(2, "little")
        buf[7:9] = battery_mv.to_bytes(2, "little")
        return bytes(buf)

    def _v2(
        self,
        hw_type: int = 0x0042,
        fw_version: int = 0x0100,
        battery_mv: int = 3000,
        temperature: int = 22,
    ) -> bytes:
        buf = bytearray(11)
        buf[0] = 2
        buf[1:3] = hw_type.to_bytes(2, "little")
        buf[3:5] = fw_version.to_bytes(2, "little")
        buf[7:9] = battery_mv.to_bytes(2, "little")
        buf[9:10] = struct.pack("<b", temperature)
        return bytes(buf)

    def test_v1_version_field(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1()).version == 1

    def test_v1_no_temperature(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1()).temperature is None

    def test_v1_hw_type(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1(hw_type=0x0042)).hw_type == 0x0042

    def test_v1_fw_version(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1(fw_version=0x0200)).fw_version == 0x0200

    def test_v1_battery_mv(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1(battery_mv=3000)).battery_mv == 3000

    def test_v1_battery_percentage_at_full(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v1(battery_mv=3200)).battery_pct == 100

    def test_v2_version_field(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v2()).version == 2

    def test_v2_temperature_positive(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v2(temperature=22)).temperature == 22

    def test_v2_temperature_negative(self, protocol: ATCProtocol):
        assert protocol.parse_advertising_data(self._v2(temperature=-5)).temperature == -5

    def test_empty_data_raises(self, protocol: ATCProtocol):
        with pytest.raises(ValueError, match="Empty"):
            protocol.parse_advertising_data(b"")

    def test_v1_too_short_raises(self, protocol: ATCProtocol):
        with pytest.raises(ValueError):
            protocol.parse_advertising_data(bytes([1]) + bytes(8))  # 9 bytes, needs 10

    def test_v2_too_short_raises(self, protocol: ATCProtocol):
        with pytest.raises(ValueError):
            protocol.parse_advertising_data(bytes([2]) + bytes(9))  # 10 bytes, needs 11

    def test_unknown_version_raises(self, protocol: ATCProtocol):
        with pytest.raises(ValueError, match="Unsupported"):
            protocol.parse_advertising_data(bytes([99]) + bytes(15))


class TestInterrogateDevice:
    async def test_width_and_height_parsed(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_display_info_response(width=296, height=128, colors=1))
        caps = await protocol.interrogate_device(conn)
        assert caps.width == 296
        assert caps.height == 128

    async def test_mono_color_scheme(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_display_info_response(width=296, height=128, colors=1))
        caps = await protocol.interrogate_device(conn)
        assert caps.color_scheme == 0

    async def test_two_colors_defaults_to_bwr(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_display_info_response(width=296, height=128, colors=2))
        caps = await protocol.interrogate_device(conn)
        assert caps.color_scheme == 1

    async def test_three_colors_gives_bwry(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_display_info_response(width=296, height=128, colors=3))
        caps = await protocol.interrogate_device(conn)
        assert caps.color_scheme == 3

    async def test_wh_inverted_swaps_dimensions(self, protocol: ATCProtocol, mock_connection_factory):
        # Device encodes width=184, height=384 with wh_inverted=True.
        # Parser applies: final_width=height=384, final_height=width=184.
        conn = mock_connection_factory(build_display_info_response(width=184, height=384, colors=1, wh_inverted=True))
        caps = await protocol.interrogate_device(conn)
        assert caps.width == 384
        assert caps.height == 184

    async def test_response_too_short_raises(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(bytes(10))
        with pytest.raises(BLEProtocolError, match="Invalid response length"):
            await protocol.interrogate_device(conn)

    async def test_wrong_command_id_raises(self, protocol: ATCProtocol, mock_connection_factory):
        buf = bytearray(33)
        buf[0] = 0x00
        buf[1] = 0x99  # wrong cmd
        conn = mock_connection_factory(bytes(buf))
        with pytest.raises(BLEProtocolError, match="Invalid command ID"):
            await protocol.interrogate_device(conn)

    async def test_response_exactly_min_length_minus_one_raises(self, protocol: ATCProtocol, mock_connection_factory):
        # BLE_MIN_RESPONSE_LENGTH is 33; anything shorter is caught before payload check
        conn = mock_connection_factory(bytes(32))
        with pytest.raises(BLEProtocolError, match="Invalid response length"):
            await protocol.interrogate_device(conn)


class TestReadDeviceConfig:
    async def test_base_fields_parsed(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(
            build_dynamic_config_response(screen_type=7, hw_type=0x0042, screen_w=296, screen_h=128)
        )
        config = await protocol.read_device_config(conn)
        assert config.screen_type == 7
        assert config.hw_type == 0x0042
        assert config.screen_w == 296
        assert config.screen_h == 128

    async def test_all_pinouts_none_when_disabled(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_dynamic_config_response())
        config = await protocol.read_device_config(conn)
        assert config.epd_pinout is None
        assert config.led_pinout is None
        assert config.nfc_pinout is None
        assert config.flash_pinout is None

    async def test_flags_disabled_when_zero(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(build_dynamic_config_response())
        config = await protocol.read_device_config(conn)
        assert config.epd_enabled is False
        assert config.led_enabled is False
        assert config.nfc_enabled is False
        assert config.flash_enabled is False

    async def test_response_too_short_raises(self, protocol: ATCProtocol, mock_connection_factory):
        conn = mock_connection_factory(bytes(10))
        with pytest.raises(BLEProtocolError, match="too short"):
            await protocol.read_device_config(conn)

    async def test_wrong_prefix_raises(self, protocol: ATCProtocol, mock_connection_factory):
        bad = bytes([0x00, 0xAA]) + bytes(43)
        conn = mock_connection_factory(bad)
        with pytest.raises(BLEProtocolError, match="Unexpected response prefix"):
            await protocol.read_device_config(conn)
