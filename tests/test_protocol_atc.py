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
        # Reported in the orientation the panel displays, which is a quarter
        # turn from the buffer the device is sent, so the two fields swap
        # relative to how they arrive on the wire.
        conn = mock_connection_factory(build_display_info_response(width=296, height=128, colors=1))
        caps = await protocol.interrogate_device(conn)
        assert caps.width == 128
        assert caps.height == 296

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
        # wh_inverted_ble cancels the swap rather than causing one: the device
        # already reports these the other way round, so the panel displays
        # 184x384 and that is what a caller draws for.
        conn = mock_connection_factory(build_display_info_response(width=184, height=384, colors=1, wh_inverted=True))
        caps = await protocol.interrogate_device(conn)
        assert caps.width == 184
        assert caps.height == 384

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


# ATC_02AF11 (Hanshow Nebular 350Y-N) on an ATC build with the GUI-rotation byte, set to type 1.
_CFG_WITH_ROTATION = bytes.fromhex(
    "00cd0100600001000000008001b800000000000200000000004e3a8400683a84006f3a8400000000000801020100"
    "10038003020000001001000020014001200280010100000101010403080380000001020202400210020000000000000000"
)
# The same config as firmware without the byte sends it.
_CFG_WITHOUT_ROTATION = _CFG_WITH_ROTATION[:45] + _CFG_WITH_ROTATION[46:]


class TestReadDeviceConfigLayouts:
    @pytest.mark.parametrize("raw", [_CFG_WITH_ROTATION, _CFG_WITHOUT_ROTATION])
    async def test_pins_read_the_same_with_and_without_rotation_byte(
        self, protocol: ATCProtocol, mock_connection_factory, raw
    ):
        cfg = await protocol.read_device_config(mock_connection_factory(raw))
        epd = cfg.epd_pinout
        assert (epd.reset, epd.dc, epd.busy, epd.cs, epd.clk, epd.mosi) == (
            0x0310,
            0x0380,
            0x0002,
            0x0110,
            0x0120,
            0x0140,
        )
        assert (epd.enable, epd.enable1, epd.enable_invert) == (0x0220, 0x0180, True)
        assert (cfg.led_pinout.r, cfg.led_pinout.g, cfg.led_pinout.b) == (0x0304, 0x0308, 0x0080)
        assert (cfg.screen_type, cfg.screen_w, cfg.screen_h, cfg.adc_pinout) == (1, 184, 384, 0x0108)
        assert cfg.gui_rotation == 0
