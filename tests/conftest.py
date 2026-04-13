"""Pytest configuration and shared fixtures."""

import struct

import pytest


class MockBLEConnection:
    """Minimal mock of BLEConnection for protocol parsing tests."""

    mac_address = "AA:BB:CC:DD:EE:FF"

    def __init__(self, response: bytes) -> None:
        self._response = response

    async def write_command_with_response(self, _command: bytes) -> bytes:
        return self._response


@pytest.fixture
def mock_connection_factory():
    """Return a factory that creates a MockBLEConnection with a preset response."""

    def factory(response: bytes) -> MockBLEConnection:
        return MockBLEConnection(response)

    return factory


def build_display_info_response(
    width: int,
    height: int,
    colors: int,
    wh_inverted: bool = False,
) -> bytes:
    """Build a synthetic CMD_GET_DISPLAY_INFO (0x0005) response for testing.

    The ATC firmware response layout is:
    - Bytes 0–1:  Command ID  [0x00, 0x05]
    - Bytes 2+:   Payload (minimum 31 bytes)
        - payload[19]    → index 21: wh_inverted flag (0 or 1)
        - payload[22:24] → index 24:26: height as uint16 little-endian
        - payload[24:26] → index 26:28: width  as uint16 little-endian
        - payload[30]    → index 32:   color count (1=mono, 2=BWR/BWY, 3=BWRY)

    Total buffer size: 33 bytes (2-byte header + 31-byte payload).
    Bytes not listed above are unused by the parser — leave them as 0x00.

    Args:
        width: Display width in pixels
        height: Display height in pixels
        colors: Color count (1, 2, or 3)
        wh_inverted: Whether the device reports swapped width/height

    Returns:
        33-byte response ready to feed into ATCProtocol.interrogate_device()

    """
    buf = bytearray(33)
    buf[0] = 0x00
    buf[1] = 0x05
    buf[21] = 1 if wh_inverted else 0  # payload[19]
    struct.pack_into("<H", buf, 24, height)  # payload[22:24]
    struct.pack_into("<H", buf, 26, width)  # payload[24:26]
    buf[32] = colors  # payload[30]
    return bytes(buf)


def build_dynamic_config_response(
    screen_type: int = 7,
    hw_type: int = 0x0042,
    screen_w: int = 296,
    screen_h: int = 128,
    screen_colors: int = 2,
) -> bytes:
    """Build a minimal CMD_GET_DYNAMIC_CONFIG (0x00CD) response for testing.

    All optional pinout sections are disabled, so the response is exactly
    DYNAMIC_CONFIG_MIN_LENGTH (45) bytes: 2-byte prefix + 43-byte base struct.
    """
    prefix = bytes([0x00, 0xCD])
    base = struct.pack(
        "<HHHbHHHHHHHHIIIIHH",
        screen_type,  # screen_type
        hw_type,  # hw_type
        0,  # screen_functions
        0,  # wh_inv_ble (signed byte)
        0,  # wh_inverted
        screen_h,  # screen_h
        screen_w,  # screen_w
        0,  # screen_h_offset
        0,  # screen_w_offset
        screen_colors,  # screen_colors
        0,  # black_invert
        0,  # second_color_invert
        0,  # epd_en = disabled
        0,  # led_en = disabled
        0,  # nfc_en = disabled
        0,  # flash_en = disabled
        0,  # adc_pinout
        0,  # uart_pinout
    )
    return prefix + base
