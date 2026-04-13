"""ATC firmware protocol implementation."""

import logging
import struct
from typing import TYPE_CHECKING

from ..exceptions import BLEProtocolError
from ..models.advertising import AdvertisingData
from ..models.capabilities import DeviceCapabilities
from ..models.device_config import DeviceConfig, EPDPinout, FlashPinout, LEDPinout, NFCPinout
from .constants import (
    BLE_MIN_RESPONSE_LENGTH,
    CMD_GET_DISPLAY_INFO,
    CMD_GET_DYNAMIC_CONFIG,
    DYNAMIC_CONFIG_MIN_LENGTH,
    DYNAMIC_CONFIG_RESPONSE_PREFIX,
)

if TYPE_CHECKING:
    from ..transport.connection import BLEConnection

_LOGGER = logging.getLogger(__name__)


class ATCProtocol:
    """ATC firmware protocol implementation.

    Supports the original ATC BLE firmware protocol with:
    - Manufacturer ID: 0x1337 (4919)
    - Service UUID: 00001337-0000-1000-8000-00805f9b34fb
    - Interrogation: CMD_GET_DISPLAY_INFO (0x0005)
    - Advertising: Version 1 (10 bytes) and Version 2 (11 bytes with temperature)
    """

    @staticmethod
    def _calculate_battery_percentage(voltage_mv: int) -> int:
        """Convert battery voltage (mV) to percentage estimate.

        Args:
            voltage_mv: Battery voltage in millivolts

        Returns:
            Battery percentage (0-100)
        """
        if voltage_mv == 0:
            return 0  # Unknown battery level

        voltage = voltage_mv / 1000.0
        min_voltage, max_voltage = 2.6, 3.2  # Battery voltage range
        percentage = min(100, max(0, int((voltage - min_voltage) * 100 / (max_voltage - min_voltage))))
        return percentage

    def parse_advertising_data(self, data: bytes) -> AdvertisingData:
        """Parse ATC manufacturer data for device state updates.

        Supports two advertising formats:
        - Version 1: 10 bytes (no temperature)
        - Version 2: 11 bytes (with temperature)

        Args:
            data: Manufacturer-specific advertising data

        Returns:
            AdvertisingData: Parsed advertising information

        Raises:
            ValueError: If data format is invalid
        """
        if not data:
            raise ValueError("Empty advertising data")

        try:
            version = data[0]

            if version == 1:
                if len(data) < 10:
                    raise ValueError(f"Version 1 requires 10 bytes, got {len(data)}")

                hw_type = int.from_bytes(data[1:3], "little")
                fw_version = int.from_bytes(data[3:5], "little")
                battery_mv = int.from_bytes(data[7:9], "little")
                battery_pct = self._calculate_battery_percentage(battery_mv)

                return AdvertisingData(
                    battery_mv=battery_mv,
                    battery_pct=battery_pct,
                    temperature=None,  # Not available in version 1
                    hw_type=hw_type,
                    fw_version=fw_version,
                    version=version,
                )

            elif version == 2:
                if len(data) < 11:
                    raise ValueError(f"Version 2 requires 11 bytes, got {len(data)}")

                hw_type = int.from_bytes(data[1:3], "little")
                fw_version = int.from_bytes(data[3:5], "little")
                battery_mv = int.from_bytes(data[7:9], "little")
                battery_pct = self._calculate_battery_percentage(battery_mv)
                temperature = struct.unpack("<b", data[9:10])[0]

                return AdvertisingData(
                    battery_mv=battery_mv,
                    battery_pct=battery_pct,
                    temperature=temperature,
                    hw_type=hw_type,
                    fw_version=fw_version,
                    version=version,
                )

            else:
                raise ValueError(f"Unsupported advertising data version: {version}")

        except (IndexError, struct.error) as e:
            raise ValueError(f"Error parsing ATC advertising data: {e}") from e

    async def interrogate_device(self, connection: "BLEConnection") -> DeviceCapabilities:
        """Query device using CMD_GET_DISPLAY_INFO (0x0005).

        Connects to device and retrieves display specifications including:
        - Display dimensions (width, height)
        - Color support capabilities
        - Buffer rotation requirement

        Args:
            connection: Active BLE connection to device

        Returns:
            DeviceCapabilities: Device information

        Raises:
            BLEProtocolError: If interrogation fails or response is invalid
        """
        # Request display information using protocol command 0005
        response = await connection.write_command_with_response(CMD_GET_DISPLAY_INFO)

        _LOGGER.debug(
            "ATC device interrogation for %s: received %d bytes",
            connection.mac_address,
            len(response),
        )

        # Verify response format: 00 05 + payload
        if len(response) < BLE_MIN_RESPONSE_LENGTH:
            raise BLEProtocolError(
                f"Invalid response length: {len(response)} bytes (expected at least {BLE_MIN_RESPONSE_LENGTH})"
            )

        # Verify command ID (should be 0x0005)
        if response[0] != 0x00 or response[1] != 0x05:
            raise BLEProtocolError(f"Invalid command ID in response: {response[0]:02x}{response[1]:02x}")

        # Skip command ID (first 2 bytes) and parse payload
        payload = response[2:]

        if len(payload) < 31:
            raise BLEProtocolError("Response payload too short")

        # Parse display specifications from 0005 response:

        wh_inverted = payload[19] == 1
        height = struct.unpack("<H", payload[22:24])[0]
        width = struct.unpack("<H", payload[24:26])[0]
        colors = payload[30]

        # Determine color support from device response
        if colors >= 3:
            color_scheme = 3  # BWRY
        elif colors >= 2:
            color_scheme = 1  # BWR (default for 2-color, refined later)
        else:
            color_scheme = 0  # MONO

        _LOGGER.info(
            "ATC device %s raw dimensions: width=%d, height=%d, colors=%d, wh_inverted=%s",
            connection.mac_address,
            width,
            height,
            colors,
            wh_inverted,
        )

        # Apply inversion if needed
        final_width = height if wh_inverted else width
        final_height = width if wh_inverted else height

        _LOGGER.info(
            "ATC device %s final dimensions: %dx%d (color_scheme=%d)",
            connection.mac_address,
            final_width,
            final_height,
            color_scheme,
        )

        return DeviceCapabilities(
            width=final_width,
            height=final_height,
            color_scheme=color_scheme,
        )

    async def read_device_config(self, connection: "BLEConnection") -> DeviceConfig:
        """Read full device configuration using CMD_GET_DYNAMIC_CONFIG (0x0011).

        Sends 0x0011 and parses the 0x00CD response which contains all device
        settings including hw_type (OEPL device type), screen dimensions/offsets,
        color config, and optional GPIO pinout sections.

        Args:
            connection: Active BLE connection to device

        Returns:
            DeviceConfig with all parsed settings

        Raises:
            BLEProtocolError: If the response is invalid or too short
        """
        response = await connection.write_command_with_response(CMD_GET_DYNAMIC_CONFIG)

        if len(response) < DYNAMIC_CONFIG_MIN_LENGTH:
            raise BLEProtocolError(
                f"Dynamic config response too short: {len(response)} bytes"
                f" (expected at least {DYNAMIC_CONFIG_MIN_LENGTH})"
            )

        if response[:2] != DYNAMIC_CONFIG_RESPONSE_PREFIX:
            raise BLEProtocolError(
                f"Unexpected response prefix: {response[:2].hex()} (expected {DYNAMIC_CONFIG_RESPONSE_PREFIX.hex()})"
            )

        # Parse base config (43 bytes starting at offset 2, after 00CD prefix)
        # Layout: screen_type(H) hw_type(H) functions(H) wh_inv_ble(B)
        #         wh_inv(H) h(H) w(H) h_off(H) w_off(H) colors(H)
        #         black_inv(H) color_inv(H)
        #         epd_en(I) led_en(I) nfc_en(I) flash_en(I)
        #         adc(H) uart(H)
        (
            screen_type,
            hw_type,
            screen_functions,
            wh_inv_ble_raw,
            wh_inverted_raw,
            screen_h,
            screen_w,
            screen_h_offset,
            screen_w_offset,
            screen_colors,
            black_invert_raw,
            second_color_invert_raw,
            epd_en_raw,
            led_en_raw,
            nfc_en_raw,
            flash_en_raw,
            adc_pinout,
            uart_pinout,
        ) = struct.unpack_from("<HHHbHHHHHHHHIIIIHH", response, offset=2)

        epd_enabled = epd_en_raw != 0
        led_enabled = led_en_raw != 0
        nfc_enabled = nfc_en_raw != 0
        flash_enabled = flash_en_raw != 0

        offset = 2 + struct.calcsize("<HHHbHHHHHHHHIIIIHH")

        epd_pinout: EPDPinout | None = None
        if epd_enabled and offset + 26 <= len(response):
            # 10× uint16, 1× uint8, 1× uint16, 3× uint8  = 26 bytes
            epd_regs = struct.unpack_from("<HHHHHHHHHH", response, offset)
            reset, dc, busy, busy_s, cs, cs_s, clk, mosi, enable, enable1 = epd_regs
            offset += struct.calcsize("<HHHHHHHHHH")
            enable_invert = struct.unpack_from("<B", response, offset)[0] != 0
            offset += 1
            flash_cs = struct.unpack_from("<H", response, offset)[0]
            offset += 2
            pin_config_sleep, pin_enable, pin_enable_sleep = struct.unpack_from("<BBB", response, offset)
            offset += 3
            epd_pinout = EPDPinout(
                reset=reset,
                dc=dc,
                busy=busy,
                busy_s=busy_s,
                cs=cs,
                cs_s=cs_s,
                clk=clk,
                mosi=mosi,
                enable=enable,
                enable1=enable1,
                enable_invert=enable_invert,
                flash_cs=flash_cs,
                pin_config_sleep=pin_config_sleep,
                pin_enable=pin_enable,
                pin_enable_sleep=pin_enable_sleep,
            )

        led_pinout: LEDPinout | None = None
        if led_enabled and offset + 7 <= len(response):
            r, g, b = struct.unpack_from("<HHH", response, offset)
            offset += 6
            inverted = struct.unpack_from("<B", response, offset)[0] != 0
            offset += 1
            led_pinout = LEDPinout(r=r, g=g, b=b, inverted=inverted)

        nfc_pinout: NFCPinout | None = None
        if nfc_enabled and offset + 8 <= len(response):
            sda, scl, cs, irq = struct.unpack_from("<HHHH", response, offset)
            offset += 8
            nfc_pinout = NFCPinout(sda=sda, scl=scl, cs=cs, irq=irq)

        flash_pinout: FlashPinout | None = None
        if flash_enabled and offset + 8 <= len(response):
            cs, clk, miso, mosi = struct.unpack_from("<HHHH", response, offset)
            offset += 8
            flash_pinout = FlashPinout(cs=cs, clk=clk, miso=miso, mosi=mosi)

        _LOGGER.debug(
            "Device config for %s: hw_type=0x%04x screen=%dx%d colors=%d epd=%s led=%s nfc=%s flash=%s",
            connection.mac_address,
            hw_type,
            screen_w,
            screen_h,
            screen_colors,
            epd_enabled,
            led_enabled,
            nfc_enabled,
            flash_enabled,
        )

        return DeviceConfig(
            screen_type=screen_type,
            hw_type=hw_type,
            screen_functions=screen_functions,
            wh_inverted_ble=wh_inv_ble_raw != 0,
            wh_inverted=wh_inverted_raw != 0,
            screen_h=screen_h,
            screen_w=screen_w,
            screen_h_offset=screen_h_offset,
            screen_w_offset=screen_w_offset,
            screen_colors=screen_colors,
            black_invert=black_invert_raw != 0,
            second_color_invert=second_color_invert_raw != 0,
            epd_enabled=epd_enabled,
            led_enabled=led_enabled,
            nfc_enabled=nfc_enabled,
            flash_enabled=flash_enabled,
            adc_pinout=adc_pinout,
            uart_pinout=uart_pinout,
            epd_pinout=epd_pinout,
            led_pinout=led_pinout,
            nfc_pinout=nfc_pinout,
            flash_pinout=flash_pinout,
        )
