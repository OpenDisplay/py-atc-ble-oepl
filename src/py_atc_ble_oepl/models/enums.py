"""Enums for image transforms and device configuration."""

from enum import IntEnum


class FitMode(IntEnum):
    """Image fit strategies for mapping source images to display dimensions."""

    STRETCH = 0  # Distort to fill exact dimensions (ignores aspect ratio)
    CONTAIN = 1  # Scale to fit within bounds, pad empty space with white
    COVER = 2  # Scale to cover bounds, crop overflow (no distortion)
    CROP = 3  # No scaling, center-crop at native resolution (pad if smaller)


class Rotation(IntEnum):
    """Additional image rotation applied before upload (additive on top of device rotation)."""

    ROTATE_0 = 0
    ROTATE_90 = 90
    ROTATE_180 = 180
    ROTATE_270 = 270
