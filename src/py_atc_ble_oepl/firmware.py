"""The ATC firmware image: where it is published, checking it, and its version.

atc1441 publishes one image, ``ATC_BLE_OEPL.bin``, for the Telink TLSR825x
tags the firmware runs on, with no version list beside it. The version is
read from the image itself (:func:`firmware_version`).

Tags install an image sent as a firmware update (data type 0x03) through the
same block transfer as an image (``ATC_BLE_OEPL_Image_Upload.html``,
``sendFw``). Before installing, the tag checks it the way Telink's
``check_fw`` builds it, and keeps its own firmware if the check fails;
:meth:`ATCFirmware.from_bytes` runs the same check, so a damaged download is
never sent.
"""

from __future__ import annotations

import re
import struct
import zlib
from dataclasses import dataclass

from .exceptions import ATCError

FIRMWARE_URL = "https://raw.githubusercontent.com/atc1441/atc1441.github.io/main/ATC_BLE_OEPL.bin"

# Data type of a firmware update in the block transfer (oepl-definitions.h).
DATATYPE_FW_UPDATE = 0x03

_MAGIC_OFFSET = 8
_MAGIC = b"KNLT"
_SIZE_OFFSET = 24

# Early in the image the firmware loads its version as an 8-bit immediate.
# Around it, whatever registers the compiler picked:
#   ?? f2 ?? 03 RR 21 [version] a2|a3 (RR + 0x40) 21
# Found by comparing atc1441's builds around his "Version increase from 84 to
# 85" commit, and it reads a rising version from every build he has
# published since 2024-12-10.
_VERSION_SITE = re.compile(rb".\xf2.\x03(.)\x21(.)[\xa2\xa3](.)\x21", re.DOTALL)
_VERSION_SEARCH_END = 4096


class FirmwareError(ATCError):
    """A firmware image is not one a tag would install."""


def _telink_crc(data: bytes) -> int:
    # Standard CRC-32 without the final inversion, as Telink's check_fw.
    return zlib.crc32(data) ^ 0xFFFFFFFF


def firmware_version(data: bytes) -> int | None:
    """Return the version an ATC firmware image carries, as tags report it.

    Tags report it in their advertisement (``AdvertisingData.fw_version``).
    Returns ``None`` if the image does not have the code it is read from,
    which a future build could change.
    """
    for match in _VERSION_SITE.finditer(data, 0, _VERSION_SEARCH_END):
        if match[3][0] == (match[1][0] + 0x40) & 0xFF:
            return match[2][0]
    return None


@dataclass(frozen=True)
class ATCFirmware:
    """An ATC firmware image a tag would install."""

    data: bytes = b""
    # None if it could not be read from the image.
    version: int | None = None

    @classmethod
    def from_bytes(cls, data: bytes) -> ATCFirmware:
        """Check *data* is an image a tag would install, and read its version.

        A Telink image carries "KNLT" at offset 8 and its total length at
        offset 24, and ends in a CRC32 of everything before it, appended to a
        body padded to 16 bytes.

        Raises:
            FirmwareError: If any of that does not hold.
        """
        problems = []
        if len(data) < _SIZE_OFFSET + 8:
            raise FirmwareError(f"Not a Telink firmware image: only {len(data)} bytes")
        if data[_MAGIC_OFFSET : _MAGIC_OFFSET + 4] != _MAGIC:
            problems.append("no KNLT header")
        declared = struct.unpack_from("<I", data, _SIZE_OFFSET)[0]
        if declared != len(data):
            problems.append(f"length field {declared} does not match its {len(data)} bytes")
        if len(data) % 16 != 4:
            problems.append(f"{len(data)} bytes is not a padded body plus CRC")
        stored = struct.unpack_from("<I", data, len(data) - 4)[0]
        if stored != _telink_crc(data[:-4]):
            problems.append("its CRC does not match")
        if problems:
            raise FirmwareError("Not a firmware image a tag would install: " + ", ".join(problems))
        return cls(data, firmware_version(data))
