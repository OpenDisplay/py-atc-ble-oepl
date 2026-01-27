"""Image encoding functions for ATC BLE devices."""

import struct
import zlib
from enum import Enum

import numpy as np
from PIL import Image

# BLE Protocol Sizes
BLE_BLOCK_SIZE = 4096
BLE_MAX_PACKET_DATA_SIZE = 230


class BLEDataType(Enum):
    """BLE image data types."""

    RAW_BW = 0x20  # Uncompressed monochrome
    RAW_COLOR = 0x21  # Uncompressed color (BWR/BWY)
    COMPRESSED = 0x30  # Compressed image


def create_data_info(
    checksum: int,
    data_ver: int,
    data_size: int,
    data_type: int,
    data_type_argument: int,
    next_check_in: int,
) -> bytes:
    """Create data info packet for image upload.

    Args:
        checksum: Data checksum (usually 255 placeholder)
        data_ver: CRC32 of image data
        data_size: Image data size in bytes
        data_type: Data type enum value (0x20, 0x21, 0x30)
        data_type_argument: Additional argument (usually 0)
        next_check_in: Next check-in time (usually 0)

    Returns:
        Packed data info structure
    """
    return struct.pack(
        "<BQIBBH",
        checksum,
        data_ver,
        data_size,
        data_type,
        data_type_argument,
        next_check_in,
    )


def create_block_part(block_id: int, part_id: int, data: bytes) -> bytearray:
    """Create a block part packet for image upload.

    Args:
        block_id: Block identifier
        part_id: Part identifier within block
        data: Packet data (max 230 bytes)

    Returns:
        Block part packet with checksum

    Raises:
        ValueError: If data exceeds maximum size
    """
    max_data_size = 230
    data_length = len(data)
    if data_length > max_data_size:
        raise ValueError("Data length exceeds maximum allowed size for a packet.")

    buffer = bytearray(3 + max_data_size)  # Always 233 bytes, zero-filled
    buffer[1] = block_id & 0xFF
    buffer[2] = part_id & 0xFF
    buffer[3 : 3 + data_length] = data
    # CRC must include entire buffer including zero padding (like JavaScript version)
    buffer[0] = sum(buffer[1:]) & 0xFF
    return buffer


def convert_image_to_bytes(image: Image.Image, color_scheme: int = 0, compressed: bool = False) -> tuple[int, bytes]:
    """Convert a PIL Image to device format.

    Expects image to be pre-quantized to exact palette colors (via dithering).
    Uses exact color matching instead of luminance-based detection.

    Supports:
    - Monochrome (1-bit)
    - Color dual-plane (BWR/BWY/BWRY)
    - Optional zlib compression

    Args:
        image: PIL Image to convert (should be pre-quantized by epaper_dithering)
        color_scheme: Color scheme int (0=mono, 1=BWR, 2=BWY, 3=BWRY)
        compressed: Whether to compress the data

    Returns:
        tuple: (data_type, pixel_array)
    """
    pixel_array = np.array(image.convert("RGB"))
    height, width, _ = pixel_array.shape

    # Get RGB channels
    r = pixel_array[:, :, 0]
    g = pixel_array[:, :, 1]
    b = pixel_array[:, :, 2]

    # Exact color matching (image already quantized by dithering)
    black_pixels = (r == 0) & (g == 0) & (b == 0)
    red_pixels = (r == 255) & (g == 0) & (b == 0)
    yellow_pixels = (r == 255) & (g == 255) & (b == 0)

    # Determine if multi-color mode
    multi_color = color_scheme in (1, 2, 3)  # BWR, BWY, or BWRY

    # Dual-plane encoding:
    # Plane 1 (BW): 1 = black or yellow, 0 = white or red
    # Plane 2 (color): 1 = red or yellow, 0 = black or white
    bw_channel_bits = black_pixels | yellow_pixels

    byte_data = np.packbits(bw_channel_bits).tobytes()
    bpp_array = bytearray(byte_data)

    if multi_color:
        color_pixels = red_pixels | yellow_pixels
        byte_data_color = np.packbits(color_pixels).tobytes()
        bpp_array += byte_data_color

    if compressed:
        buffer = bytearray(6)
        buffer[0] = 6
        buffer[1] = width & 0xFF
        buffer[2] = (width >> 8) & 0xFF
        buffer[3] = height & 0xFF
        buffer[4] = (height >> 8) & 0xFF
        buffer[5] = 0x02 if multi_color else 0x01
        buffer += bpp_array
        the_compressor = zlib.compressobj(wbits=12)
        compressed_data = the_compressor.compress(buffer)
        compressed_data += the_compressor.flush()
        return (
            BLEDataType.COMPRESSED.value,
            struct.pack("<I", len(buffer)) + compressed_data,
        )

    return (
        BLEDataType.RAW_COLOR.value if multi_color else BLEDataType.RAW_BW.value,
        bytes(bpp_array),
    )
