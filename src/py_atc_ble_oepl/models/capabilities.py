"""Device capabilities data model."""

from dataclasses import dataclass


@dataclass
class DeviceCapabilities:
    """Device display capabilities.

    Attributes:
        width: Display width in pixels
        height: Display height in pixels
        color_scheme: Color scheme code:
            - 0: MONO (black/white)
            - 1: BWR (black/white/red)
            - 2: BWY (black/white/yellow)
            - 3: BWRY (black/white/red/yellow)
            - 4: BWGBRY (6-color)
            - 5: GRAYSCALE_4 (4-level grayscale)
        rotatebuffer: Rotation flag (1=rotate 90°, 0=no rotation)
    """

    width: int
    height: int
    color_scheme: int
    rotatebuffer: int
