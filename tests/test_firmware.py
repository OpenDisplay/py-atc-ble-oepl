"""The ATC firmware image and sending it to a tag."""

import struct
import zlib

import pytest

from py_atc_ble_oepl import ATCError, ATCFirmware, FirmwareError, firmware_version
from py_atc_ble_oepl.imaging.uploader import BLEImageUploader

# The code the version is read from, as two of atc1441's builds have it:
# 2025-04-12 (version 0x54) and 2026-09-07 (0x7C), with different registers.
SITE_2025 = bytes.fromhex("524b12f20a031a2154a25a210a0a")
SITE_2026 = bytes.fromhex("5b4b1bf2130323217ca363210d90")


def _image(code: bytes = SITE_2026, size: int = 1024) -> bytes:
    """A Telink image as check_fw builds it, with *code* early on."""
    body = bytearray(b"\x00" * size)
    body[8:12] = b"KNLT"
    body[600 : 600 + len(code)] = code
    body += b"\xff" * (-len(body) % 16)
    struct.pack_into("<I", body, 24, len(body) + 4)
    crc = zlib.crc32(bytes(body)) ^ 0xFFFFFFFF
    return bytes(body) + struct.pack("<I", crc)


# ---------------------------------------------------------------------------
# The image
# ---------------------------------------------------------------------------


def test_a_well_formed_image_and_its_version():
    firmware = ATCFirmware.from_bytes(_image())
    assert firmware.version == 0x7C
    assert len(firmware.data) % 16 == 4


@pytest.mark.parametrize(("code", "version"), [(SITE_2025, 0x54), (SITE_2026, 0x7C)])
def test_version_from_both_generations_of_builds(code: bytes, version: int):
    assert firmware_version(_image(code)) == version


def test_no_version_where_the_code_is_missing():
    assert firmware_version(_image(code=b"")) is None
    # The register after the version must be the one before it plus 0x40.
    assert firmware_version(_image(code=bytes.fromhex("5b4b1bf2130323217ca364210d90"))) is None


def test_the_version_is_only_looked_for_early_in_the_image():
    image = bytearray(_image(code=b"", size=8192))
    image[5000 : 5000 + len(SITE_2026)] = SITE_2026
    assert firmware_version(bytes(image)) is None


@pytest.mark.parametrize(
    ("damage", "reason"),
    [
        (lambda b: b[:8] + b"XXXX" + b[12:], "KNLT"),
        (lambda b: b[:-4] + b"\x00\x00\x00\x00", "CRC"),
        (lambda b: b[:24] + struct.pack("<I", 1) + b[28:], "length field"),
        (lambda b: b + b"\x00" * 16, "length field"),
    ],
)
def test_a_damaged_image_is_refused(damage, reason: str):
    with pytest.raises(FirmwareError, match=reason):
        ATCFirmware.from_bytes(damage(_image()))


def test_something_too_short_to_be_an_image_is_refused():
    with pytest.raises(FirmwareError, match="only 3 bytes"):
        ATCFirmware.from_bytes(b"abc")


# ---------------------------------------------------------------------------
# Sending it
# ---------------------------------------------------------------------------


class ScriptedTag:
    """A connection that answers with *responses* in turn, recording writes."""

    mac_address = "AA:BB:CC:DD:EE:FF"

    def __init__(self, *responses: str) -> None:
        self._responses = [bytes.fromhex(r) for r in responses]
        self.writes: list[bytes] = []

    async def write_command(self, data: bytes) -> None:
        self.writes.append(data)

    async def read_response(self, timeout: float) -> bytes:
        if not self._responses:
            raise TimeoutError
        return self._responses.pop(0)


# A block request for block 0: code, checksum, data version (8), block id.
BLOCK_0 = "00C6" + "00" * 9 + "00" + "00" * 7


async def test_firmware_is_sent_as_a_firmware_update():
    tag = ScriptedTag("0063", BLOCK_0, "00C5", "00C9")
    image = _image()

    await BLEImageUploader(tag, tag.mac_address).upload_firmware(image)

    data_info = tag.writes[0]
    assert data_info[:2] == bytes.fromhex("0064")
    # checksum (1), data version (8), size (4), then the data type.
    assert struct.unpack_from("<I", data_info, 11)[0] == len(image)
    assert data_info[15] == 0x03
    # A firmware update is not an image to show.
    assert bytes.fromhex("0003") not in tag.writes


async def test_a_tag_that_takes_it_for_an_image_is_an_error():
    tag = ScriptedTag("0063", BLOCK_0, "00C5", "00C7")
    with pytest.raises(ATCError, match="UPLOAD_COMPLETE"):
        await BLEImageUploader(tag, tag.mac_address).upload_firmware(_image())


async def test_a_tag_that_stops_answering_is_an_error():
    tag = ScriptedTag("0063", BLOCK_0)
    with pytest.raises(ATCError, match="stopped answering"):
        await BLEImageUploader(tag, tag.mac_address).upload_firmware(_image())
