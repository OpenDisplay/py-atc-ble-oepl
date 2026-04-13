"""py-atc-ble-oepl - Python package for ATC BLE firmware on OEPL e-paper tags.

Simple Python module for interacting with ATC BLE firmware on OEPL e-paper display tags.
Supports device discovery, image upload with dithering, and device interrogation.

Example usage:
    >>> from py_atc_ble_oepl import ATCDevice, discover_atc_devices
    >>> from epaper_dithering import DitherMode
    >>>
    >>> # Discover devices
    >>> devices = await discover_atc_devices(timeout=30.0)
    >>> print(f"Found {len(devices)} devices")
    >>>
    >>> # Upload image
    >>> async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    ...     await device.upload_image("image.jpg", dither_mode=DitherMode.BURKES)
"""

from epaper_dithering import ColorScheme, DitherMode

from .device import ATCDevice
from .discovery import DiscoveredDevice, discover_atc_devices
from .exceptions import (
    ATCError,
    BLEConnectionError,
    BLEProtocolError,
    BLETimeoutError,
    ProtocolError,
)
from .models.capabilities import DeviceCapabilities
from .models.device_config import DeviceConfig
from .models.device_types import DEVICE_TYPES, SCREEN_TYPE_COLOR_SCHEME, get_device_type_name
from .models.enums import FitMode, Rotation
from .protocol.constants import MANUFACTURER_ID, SERVICE_UUID

__version__ = "0.2.1"

__all__ = [
    # Main API
    "ATCDevice",
    "discover_atc_devices",
    # Data structures
    "DiscoveredDevice",
    "DeviceCapabilities",
    "DeviceConfig",
    # Enums (re-exported from epaper_dithering)
    "ColorScheme",
    "DitherMode",
    # Enums (image transforms)
    "FitMode",
    "Rotation",
    # Device type map
    "DEVICE_TYPES",
    "SCREEN_TYPE_COLOR_SCHEME",
    "get_device_type_name",
    # Exceptions
    "ATCError",
    "BLEConnectionError",
    "BLETimeoutError",
    "BLEProtocolError",
    "ProtocolError",
    # Constants
    "SERVICE_UUID",
    "MANUFACTURER_ID",
]
