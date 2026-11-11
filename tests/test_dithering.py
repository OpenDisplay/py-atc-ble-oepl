"""Dithering to an ATC display's colour scheme, in the colours the encoder reads."""

import pytest
from epaper_dithering import DitherMode
from PIL import Image

from py_atc_ble_oepl import ColorScheme
from py_atc_ble_oepl.device import dither_for_scheme
from py_atc_ble_oepl.imaging.encoding import convert_image_to_bytes

WHITE, BLACK, RED, YELLOW = (255, 255, 255), (0, 0, 0), (255, 0, 0), (255, 255, 0)


@pytest.mark.parametrize(
    ("scheme", "names", "accent"),
    [
        (ColorScheme.MONO, ["black", "white"], "black"),
        (ColorScheme.BWR, ["black", "white", "red"], "red"),
        (ColorScheme.BWY, ["black", "white", "yellow"], "yellow"),
        (ColorScheme.BWRY, ["black", "white", "yellow", "red"], "red"),
    ],
)
def test_schemes(scheme, names, accent):
    assert ColorScheme.from_value(scheme.value) is scheme
    assert [entry.name for entry in scheme.palette.entries] == names
    assert scheme.accent_color == accent


def test_an_unknown_scheme_is_refused():
    with pytest.raises(ValueError):
        ColorScheme.from_value(4)


@pytest.mark.parametrize("mode", [DitherMode.NONE, DitherMode.ORDERED, DitherMode.FLOYD_STEINBERG])
def test_every_ink_is_sent_as_itself(mode):
    """A quarter of each ink comes out of dithering and the encoder unchanged."""
    image = Image.new("RGB", (16, 16), WHITE)
    image.paste(BLACK, (0, 0, 8, 8))
    image.paste(RED, (8, 0, 16, 8))
    image.paste(YELLOW, (0, 8, 8, 16))

    dithered = dither_for_scheme(image, ColorScheme.BWRY, mode)

    assert dithered.convert("RGB").tobytes() == image.tobytes()
    assert convert_image_to_bytes(dithered, ColorScheme.BWRY) == convert_image_to_bytes(image, ColorScheme.BWRY)
