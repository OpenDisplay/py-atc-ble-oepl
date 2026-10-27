"""BLE image uploader for ATC devices."""

import asyncio
import logging
import math
import zlib
from collections.abc import Callable
from enum import Enum
from typing import TYPE_CHECKING

from PIL import Image

from ..exceptions import ATCError
from ..firmware import DATATYPE_FW_UPDATE
from .encoding import (
    BLE_BLOCK_SIZE,
    BLE_MAX_PACKET_DATA_SIZE,
    convert_image_to_bytes,
    create_block_part,
    create_data_info,
)

if TYPE_CHECKING:
    from ..transport.connection import BLEConnection

_LOGGER = logging.getLogger(__name__)


class BLEResponse(Enum):
    """BLE upload response codes."""

    CMD_ACK = "0063"
    BLOCK_REQUEST = "00C6"
    BLOCK_PART_ACK = "00C4"
    BLOCK_PART_CONTINUE = "00C5"
    UPLOAD_COMPLETE = "00C7"
    IMAGE_ALREADY_DISPLAYED = "00C8"
    # The tag stored a firmware update and installs it as it restarts.
    FIRMWARE_UPDATED = "00C9"


class BLECommand(Enum):
    """BLE upload command codes."""

    DATA_INFO = "0064"
    BLOCK_PART = "0065"


class BLEImageUploader:
    """BLE image uploader for ATC devices using block-based protocol.

    Handles the block-based upload protocol for transferring images to
    ATC BLE e-paper display tags.
    """

    def __init__(
        self,
        connection: "BLEConnection",
        mac_address: str,
        progress_callback: Callable[[int, int], None] | None = None,
    ):
        """Initialize image uploader.

        Args:
            connection: Active BLE connection to device
            mac_address: Device MAC address for logging
            progress_callback: Optional callback(bytes_sent, total_bytes) called after each block
        """
        self.connection = connection
        self.mac_address = mac_address
        self._progress_callback = progress_callback

        # Upload state
        self._img_array: bytes = b""
        self._img_array_len: int = 0
        self._total_blocks: int = 0
        self._packets: list[bytearray] = []
        self._packet_index: int = 0
        self._current_block_id: int | None = None
        self._upload_complete: asyncio.Event = asyncio.Event()
        self._upload_error: str | None = None
        self._outcome: BLEResponse | None = None

    async def upload_image_block_based(self, image: Image.Image, color_scheme: int, compress: bool = True) -> bool:
        """Upload image using block-based protocol.

        Args:
            image: PIL Image to upload (pre-dithered and sized)
            color_scheme: Color scheme code (0=MONO, 1=BWR, 2=BWY, 3=BWRY)
            compress: Whether to compress image data (default: True)

        Returns:
            True if upload succeeded, False otherwise
        """
        try:
            # Convert image to device format
            data_type, pixel_array = convert_image_to_bytes(image, color_scheme, compressed=compress)

            _LOGGER.debug(
                "Upload for %s: DataType=0x%02x, DataLen=%d",
                self.mac_address,
                data_type,
                len(pixel_array),
            )
            _LOGGER.info(
                "Starting BLE image upload to %s (%d bytes)",
                self.mac_address,
                len(pixel_array),
            )

            outcome = await self._transfer(pixel_array, data_type)
            if outcome not in (BLEResponse.UPLOAD_COMPLETE, BLEResponse.IMAGE_ALREADY_DISPLAYED):
                raise ATCError(f"Tag answered the image with {outcome.name if outcome else None}")
            # Show it.
            await self.connection.write_command(bytes.fromhex("0003"))
            _LOGGER.info("BLE image upload completed successfully for %s", self.mac_address)
            return True

        except Exception as e:
            _LOGGER.error("Image upload failed for %s: %s", self.mac_address, e)
            return False

    async def upload_firmware(self, data: bytes) -> None:
        """Send a firmware image, which the tag installs as it restarts.

        Returns once the tag reports the image stored (0x00C9). The tag checks
        the image before installing it and keeps its own firmware if the check
        fails, so success is only certain once it reports the new version.

        Raises:
            ATCError: If the tag stops answering or answers otherwise.
        """
        _LOGGER.info("Starting BLE firmware upload to %s (%d bytes)", self.mac_address, len(data))
        outcome = await self._transfer(data, DATATYPE_FW_UPDATE)
        if outcome is not BLEResponse.FIRMWARE_UPDATED:
            raise ATCError(f"Tag answered the firmware with {outcome.name if outcome else None}")
        _LOGGER.info("BLE firmware upload completed for %s", self.mac_address)

    async def _transfer(self, data: bytes, data_type: int) -> BLEResponse | None:
        """Announce *data* and serve the blocks the tag asks for, until it is done.

        Returns the response that ended the transfer.

        Raises:
            ATCError: If the tag stops answering.
        """
        self._img_array = data
        self._img_array_len = len(data)
        self._total_blocks = math.ceil(self._img_array_len / BLE_BLOCK_SIZE)
        self._upload_complete.clear()
        self._upload_error = None
        self._outcome = None

        data_info = create_data_info(
            255,  # checksum placeholder
            zlib.crc32(data) & 0xFFFFFFFF,
            self._img_array_len,
            data_type,
            0,  # data_type_argument
            0,  # next_check_in
        )
        await self.connection.write_command(bytes.fromhex(BLECommand.DATA_INFO.value) + data_info)

        while not self._upload_complete.is_set():
            response = await self._wait_for_response()
            if response is None:
                raise ATCError("Tag stopped answering during the transfer")
            await self._handle_response(response)
        if self._upload_error:
            raise ATCError(f"Upload failed: {self._upload_error}")
        return self._outcome

    async def _wait_for_response(self, timeout: float = 10.0) -> bytes | None:
        """Wait for next upload response with timeout.

        Args:
            timeout: Timeout in seconds

        Returns:
            Response data or None if timeout
        """
        try:
            response = await self.connection.read_response(timeout=timeout)

            # Basic validation only
            if not response or len(response) < 2:
                return None

            # Log raw response for debugging
            _LOGGER.debug("Received response: %s (%d bytes)", response.hex(), len(response))
            return response

        except Exception as e:
            # Timeout or other error
            _LOGGER.debug("No response within timeout: %s", e)
            return None

    async def _handle_response(self, response: bytes) -> bool:
        """Handle upload response from device.

        Args:
            response: Response bytes from device

        Returns:
            True to continue waiting for responses, False to exit loop
        """
        response_code = response[:2].hex().upper()

        try:
            response_enum = BLEResponse(response_code)

            match response_enum:
                case BLEResponse.CMD_ACK:
                    _LOGGER.debug("Command ACK received")
                    return True

                case BLEResponse.BLOCK_REQUEST:
                    # Device requests a specific block
                    # Block ID is at payload offset 9 (response byte 11)
                    # Payload structure: checksum(1) + version(8) + block_id(1) + type(1) + parts(6)
                    if len(response) >= 12:
                        block_id = response[11]

                        # Track current block to detect duplicates
                        if self._current_block_id == block_id:
                            _LOGGER.warning(
                                "Device re-requested block %d (already uploading). Resending from start.",
                                block_id,
                            )

                        self._current_block_id = block_id
                        _LOGGER.debug("Device requests block %d", block_id)

                        # Send CMD_PREPARE_BLOCK (0x0002) before block data (matches HTML implementation)
                        await self.connection.write_command(bytes.fromhex("0002"))
                        await asyncio.sleep(0.05)  # 50ms delay like HTML
                        await self._send_block_data(block_id)
                    else:
                        _LOGGER.warning("BLOCK_REQUEST response too short")
                    return True

                case BLEResponse.BLOCK_PART_ACK:
                    # Device acknowledges block part - resend same packet (no increment)
                    _LOGGER.debug("Block part ACK received - resending")
                    await self._send_next_block_part()
                    return True

                case BLEResponse.BLOCK_PART_CONTINUE:
                    # Device ready for next part - increment then send
                    _LOGGER.debug("Block part CONTINUE received - advancing")
                    self._packet_index += 1

                    # Check if block complete after incrementing
                    if self._packet_index >= len(self._packets):
                        _LOGGER.info(
                            "Block %d complete (%d packets sent). Waiting for next block request.",
                            self._current_block_id,
                            len(self._packets),
                        )
                        # Don't send anything - wait for device to request next block
                        return True

                    # Send next packet
                    await self._send_next_block_part()
                    return True

                case BLEResponse.UPLOAD_COMPLETE | BLEResponse.IMAGE_ALREADY_DISPLAYED | BLEResponse.FIRMWARE_UPDATED:
                    _LOGGER.info("Transfer ended: %s", response_enum.name)
                    self._current_block_id = None
                    self._packets = []
                    self._packet_index = 0
                    self._outcome = response_enum
                    self._upload_complete.set()
                    return False

        except ValueError:
            _LOGGER.warning("Unknown response code: %s", response_code)
            return True

    async def _send_block_data(self, block_id: int) -> None:
        """Send block data for specified block ID.

        Args:
            block_id: Block identifier to send
        """
        _LOGGER.debug("Building block %d for %s", block_id, self.mac_address)
        block_start = block_id * BLE_BLOCK_SIZE
        block_end = block_start + BLE_BLOCK_SIZE
        block_data = self._img_array[block_start:block_end]

        _LOGGER.debug(
            "Sending block %d: %d bytes (offset %d-%d)",
            block_id,
            len(block_data),
            block_start,
            min(block_end, len(self._img_array)),
        )

        # Add block header with length and checksum
        crc_block = sum(block_data) & 0xFFFF
        buffer = bytearray(4)
        buffer[0] = len(block_data) & 0xFF
        buffer[1] = (len(block_data) >> 8) & 0xFF
        buffer[2] = crc_block & 0xFF
        buffer[3] = (crc_block >> 8) & 0xFF
        _LOGGER.debug(
            "Block %d header: len=%d, crc=0x%04x, header_bytes=%s",
            block_id,
            len(block_data),
            crc_block,
            buffer.hex(),
        )
        block_data = bytes(buffer) + block_data
        _LOGGER.debug("Block %d first 20 bytes (with header): %s", block_id, block_data[:20].hex())

        # Create packets
        packet_count = (len(block_data) + BLE_MAX_PACKET_DATA_SIZE - 1) // BLE_MAX_PACKET_DATA_SIZE
        self._packets = []
        for i in range(packet_count):
            start = i * BLE_MAX_PACKET_DATA_SIZE
            end = start + BLE_MAX_PACKET_DATA_SIZE
            slice_data = block_data[start:end]
            packet = create_block_part(block_id, i, slice_data)
            self._packets.append(packet)
            if i == 0:  # Log first packet for debugging
                _LOGGER.debug("First packet of block %d: %s", block_id, packet[:20].hex())

        _LOGGER.debug("Created %d packets for block %d", len(self._packets), block_id)
        self._packet_index = 0
        if self._packets:
            await self._send_next_block_part()

        if self._progress_callback is not None:
            sent = min((block_id + 1) * BLE_BLOCK_SIZE, self._img_array_len)
            self._progress_callback(sent, self._img_array_len)

    async def _send_next_block_part(self) -> None:
        """Send block part packet at current index (does not increment)."""
        if self._packet_index < len(self._packets):
            packet = self._packets[self._packet_index]
            await self.connection.write_command(bytes.fromhex(BLECommand.BLOCK_PART.value) + packet)
            _LOGGER.debug("Sent block part %d/%d", self._packet_index + 1, len(self._packets))
        else:
            _LOGGER.debug("All block parts sent")
