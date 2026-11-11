"""Enums for image transforms and device configuration."""

from enum import IntEnum
from functools import cached_property

from epaper_dithering import Palette


class ColorScheme(IntEnum):
    """The colours an ATC display can show, by the firmware's value for them."""

    MONO = 0
    BWR = 1
    BWY = 2
    BWRY = 3

    @classmethod
    def from_value(cls, value: int) -> "ColorScheme":
        """The scheme for a firmware value. Raises ``ValueError`` for an unknown one."""
        return cls(value)

    @property
    def inks(self) -> dict[str, tuple[int, int, int]]:
        """Each ink's name and the colour the encoder writes it as, in palette-index order."""
        inks = {"black": (0, 0, 0), "white": (255, 255, 255)}
        if self in (ColorScheme.BWY, ColorScheme.BWRY):
            inks["yellow"] = (255, 255, 0)
        if self in (ColorScheme.BWR, ColorScheme.BWRY):
            inks["red"] = (255, 0, 0)
        return inks

    @property
    def accent_color(self) -> str:
        """The scheme's third ink, or black for a monochrome display."""
        return {ColorScheme.BWR: "red", ColorScheme.BWY: "yellow", ColorScheme.BWRY: "red"}.get(self, "black")

    @cached_property
    def palette(self) -> Palette:
        """The idealised palette to dither to. Each ink's own colour requests it, so it stays solid."""
        return Palette.from_srgb([(rgb, name, rgb) for name, rgb in self.inks.items()])


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
