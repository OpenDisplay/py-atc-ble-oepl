"""Device metadata abstraction for ATC BLE devices."""

from __future__ import annotations

from typing import Any


class DeviceMetadata:
    """Wrapper for ATC device metadata.

    Provides property-based access to device capabilities from a dictionary
    of raw metadata (typically from DeviceCapabilities).

    Args:
        raw_metadata: Dictionary containing device metadata
    """

    def __init__(self, raw_metadata: dict[str, Any]) -> None:
        """Initialize device metadata wrapper.

        Args:
            raw_metadata: Device metadata dictionary with keys:
                - width: Display width in pixels
                - height: Display height in pixels
                - color_scheme: Color scheme code (0-5)
        """
        self._metadata = raw_metadata

    @property
    def width(self) -> int:
        """Get display width in pixels.

        Returns:
            Display width, or 0 if not available
        """
        return int(self._metadata.get("width", 0))

    @property
    def height(self) -> int:
        """Get display height in pixels.

        Returns:
            Display height, or 0 if not available
        """
        return int(self._metadata.get("height", 0))

    @property
    def color_scheme(self) -> int:
        """Get color scheme code.

        Returns:
            Color scheme:
                - 0: MONO (black/white)
                - 1: BWR (black/white/red)
                - 2: BWY (black/white/yellow)
                - 3: BWRY (black/white/red/yellow)
                - 4: BWGBRY (6-color)
                - 5: GRAYSCALE_4 (4-level grayscale)
        """
        return int(self._metadata.get("color_scheme", 0))

    @property
    def hw_type(self) -> int:
        """Get hardware type identifier.

        Returns:
            Hardware type code, or 0 if not available
        """
        return int(self._metadata.get("hw_type", 0))

    @property
    def fw_version(self) -> int:
        """Get firmware version number.

        Returns:
            Firmware version number, or 0 if not available
        """
        return int(self._metadata.get("fw_version", 0))

    def formatted_fw_version(self) -> str | None:
        """Return firmware version as a decimal string.

        Returns:
            Formatted version like "105", or None if unavailable
        """
        fw = self.fw_version
        if fw == 0:
            return None
        return str(fw)

    def get_best_upload_method(self) -> str:
        """Determine the best upload method for ATC devices.

        ATC devices only support block-based upload.

        Returns:
            Upload method string: always "block" for ATC
        """
        return "block"
