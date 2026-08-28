"""Orientation: what the caller draws versus what goes on the wire.

An ATC panel displays the buffer it is sent rotated a quarter turn clockwise.
Confirmed on four tags spanning both wh_inverted_ble values, two resolutions,
both panel orientations and both colour schemes: a block written at buffer
pixel (0,0) appears at the physical top right, with the buffer's X axis
running physically downward.

So the library owes callers two things that belong together: report the size
the panel *shows*, and rotate their image into the buffer before sending. The
pre-4.0 Home Assistant integration did both -- ble/protocol_atc.py carried
``rotatebuffer=1,  # ATC devices always need 90 rotation`` -- and the port to
this library kept the dimension half and dropped the rotation, which is why
images arrived sideways.
"""

from __future__ import annotations

import pytest
from conftest import build_display_info_response
from PIL import Image

from py_atc_ble_oepl.device import _to_buffer_orientation
from py_atc_ble_oepl.protocol.atc import ATCProtocol


class TestReportedDimensions:
    """interrogate() reports the orientation the panel displays."""

    @pytest.fixture
    def protocol(self) -> ATCProtocol:
        return ATCProtocol()

    async def test_portrait_panel_reporting_swapped(self, protocol: ATCProtocol, mock_connection_factory) -> None:
        """A 2.00 inch tag: buffer 200x152, panel 152x200 portrait.

        Measured on ATC_05D611, whose wh_inverted_ble is set.
        """
        conn = mock_connection_factory(build_display_info_response(width=152, height=200, colors=2, wh_inverted=True))
        caps = await protocol.interrogate_device(conn)

        assert (caps.width, caps.height) == (152, 200)

    async def test_landscape_panel_reporting_straight(self, protocol: ATCProtocol, mock_connection_factory) -> None:
        """A 2.13 inch tag: buffer 128x250, panel 250x128 landscape.

        Measured on ATC_164840, whose wh_inverted_ble is clear.
        """
        conn = mock_connection_factory(build_display_info_response(width=128, height=250, colors=1))
        caps = await protocol.interrogate_device(conn)

        assert (caps.width, caps.height) == (250, 128)


class TestBufferOrientation:
    """The rotation that puts a caller's image the right way up."""

    def test_dimensions_are_transposed(self) -> None:
        """The buffer is the panel's size turned a quarter turn."""
        assert _to_buffer_orientation(Image.new("RGB", (152, 200))).size == (200, 152)

    def test_rotation_is_anticlockwise(self) -> None:
        """Which way round is the whole point.

        The panel turns the buffer clockwise, so the top left of what the
        caller drew has to start life at the buffer's bottom left for it to
        arrive back at the top left.
        """
        img = Image.new("RGB", (152, 200), "white")
        img.putpixel((0, 0), (255, 0, 0))

        buffer = _to_buffer_orientation(img)

        assert buffer.getpixel((0, buffer.height - 1)) == (255, 0, 0)

    def test_content_is_not_resampled(self) -> None:
        """A quarter turn is lossless, so no colour may be invented."""
        img = Image.new("RGB", (152, 200), "white")
        img.putpixel((10, 20), (255, 0, 0))

        buffer = _to_buffer_orientation(img)

        assert set(buffer.convert("RGB").getcolors()) >= {(1, (255, 0, 0))}
