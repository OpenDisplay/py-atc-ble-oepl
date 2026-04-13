"""Tests for image encoding functions."""

import struct

import pytest
from PIL import Image

from py_atc_ble_oepl.imaging.encoding import (
    BLEDataType,
    convert_image_to_bytes,
    create_block_part,
    create_data_info,
)


class TestCreateDataInfo:
    def test_output_size_matches_struct_format(self):
        result = create_data_info(
            checksum=0xFF,
            data_ver=0xDEADBEEF,
            data_size=1024,
            data_type=BLEDataType.RAW_BW.value,
            data_type_argument=0,
            next_check_in=0,
        )
        assert len(result) == struct.calcsize("<BQIBBH")

    def test_all_fields_round_trip(self):
        args = dict(
            checksum=0xAB,
            data_ver=0x1234567890ABCDEF,
            data_size=4096,
            data_type=BLEDataType.RAW_COLOR.value,
            data_type_argument=3,
            next_check_in=60,
        )
        packed = create_data_info(**args)
        checksum, data_ver, data_size, data_type, data_type_argument, next_check_in = struct.unpack("<BQIBBH", packed)
        assert checksum == args["checksum"]
        assert data_ver == args["data_ver"]
        assert data_size == args["data_size"]
        assert data_type == args["data_type"]
        assert data_type_argument == args["data_type_argument"]
        assert next_check_in == args["next_check_in"]

    def test_zero_data_ver(self):
        packed = create_data_info(0xFF, 0, 0, 0x20, 0, 0)
        _, data_ver, *_ = struct.unpack("<BQIBBH", packed)
        assert data_ver == 0


class TestCreateBlockPart:
    def test_output_is_always_233_bytes_empty_data(self):
        assert len(create_block_part(0, 0, b"")) == 233

    def test_output_is_always_233_bytes_with_data(self):
        assert len(create_block_part(0, 0, b"A" * 100)) == 233

    def test_block_id_at_byte_1(self):
        result = create_block_part(7, 0, b"")
        assert result[1] == 7

    def test_part_id_at_byte_2(self):
        result = create_block_part(0, 5, b"")
        assert result[2] == 5

    def test_data_stored_from_byte_3(self):
        data = b"hello"
        result = create_block_part(0, 0, data)
        assert result[3 : 3 + len(data)] == data

    def test_trailing_bytes_are_zero(self):
        result = create_block_part(0, 0, b"A" * 5)
        assert all(b == 0 for b in result[8:])

    def test_checksum_is_sum_of_bytes_1_onwards(self):
        result = create_block_part(0, 0, b"")
        assert result[0] == sum(result[1:]) & 0xFF

    def test_checksum_includes_zero_padding(self):
        # Only block_id contributes: block_id=1, rest zero → checksum = 1
        result = create_block_part(1, 0, b"")
        assert result[0] == 1

    def test_max_data_size_is_accepted(self):
        data = bytes(range(230))
        result = create_block_part(0, 0, data)
        assert result[3:233] == data

    def test_overflow_raises_value_error(self):
        with pytest.raises(ValueError, match="exceeds maximum"):
            create_block_part(0, 0, b"X" * 231)

    def test_block_id_masked_to_byte(self):
        result = create_block_part(0x1FF, 0, b"")
        assert result[1] == 0xFF

    def test_part_id_masked_to_byte(self):
        result = create_block_part(0, 0x1FF, b"")
        assert result[2] == 0xFF


class TestConvertImageToBytes:
    @pytest.fixture
    def white_8x4(self):
        return Image.new("RGB", (8, 4), (255, 255, 255))

    @pytest.fixture
    def black_8x4(self):
        return Image.new("RGB", (8, 4), (0, 0, 0))

    @pytest.fixture
    def red_8x4(self):
        return Image.new("RGB", (8, 4), (255, 0, 0))

    @pytest.fixture
    def yellow_8x4(self):
        return Image.new("RGB", (8, 4), (255, 255, 0))

    # --- data type selection ---

    def test_mono_returns_raw_bw_type(self, white_8x4):
        data_type, _ = convert_image_to_bytes(white_8x4, color_scheme=0)
        assert data_type == BLEDataType.RAW_BW.value

    def test_bwr_returns_raw_color_type(self, white_8x4):
        data_type, _ = convert_image_to_bytes(white_8x4, color_scheme=1)
        assert data_type == BLEDataType.RAW_COLOR.value

    def test_bwy_returns_raw_color_type(self, white_8x4):
        data_type, _ = convert_image_to_bytes(white_8x4, color_scheme=2)
        assert data_type == BLEDataType.RAW_COLOR.value

    def test_bwry_returns_raw_color_type(self, white_8x4):
        data_type, _ = convert_image_to_bytes(white_8x4, color_scheme=3)
        assert data_type == BLEDataType.RAW_COLOR.value

    def test_compressed_returns_compressed_type(self, white_8x4):
        data_type, _ = convert_image_to_bytes(white_8x4, color_scheme=0, compressed=True)
        assert data_type == BLEDataType.COMPRESSED.value

    # --- output size ---

    def test_mono_image_bw_plane_size(self, white_8x4):
        # 8×4 = 32 pixels → 4 bytes
        _, data = convert_image_to_bytes(white_8x4, color_scheme=0)
        assert len(data) == 4

    def test_color_image_two_plane_size(self, white_8x4):
        # 8×4 → 4 bytes BW + 4 bytes accent = 8 bytes
        _, data = convert_image_to_bytes(white_8x4, color_scheme=1)
        assert len(data) == 8

    # --- BW plane bit values ---

    def test_black_pixels_set_bw_plane_bits(self, black_8x4):
        _, data = convert_image_to_bytes(black_8x4, color_scheme=0)
        assert all(b == 0xFF for b in data)

    def test_white_pixels_clear_bw_plane_bits(self, white_8x4):
        _, data = convert_image_to_bytes(white_8x4, color_scheme=0)
        assert all(b == 0x00 for b in data)

    # --- accent plane bit values ---

    def test_red_pixels_set_accent_plane_not_bw(self, red_8x4):
        _, data = convert_image_to_bytes(red_8x4, color_scheme=1)
        bw_plane, accent_plane = data[:4], data[4:]
        assert all(b == 0x00 for b in bw_plane)  # red is not black
        assert all(b == 0xFF for b in accent_plane)  # red selects accent

    def test_yellow_pixels_set_both_planes(self, yellow_8x4):
        _, data = convert_image_to_bytes(yellow_8x4, color_scheme=2)
        bw_plane, accent_plane = data[:4], data[4:]
        assert all(b == 0xFF for b in bw_plane)  # yellow sets BW plane
        assert all(b == 0xFF for b in accent_plane)  # yellow sets accent plane

    def test_white_pixels_clear_both_planes_in_color_mode(self, white_8x4):
        _, data = convert_image_to_bytes(white_8x4, color_scheme=1)
        assert all(b == 0x00 for b in data)
