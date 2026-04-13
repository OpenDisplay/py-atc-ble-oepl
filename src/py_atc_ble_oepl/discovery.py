"""BLE device discovery for ATC tags."""

import asyncio
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bleak import BleakScanner

from .protocol.constants import MANUFACTURER_ID

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData

_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Information about a discovered ATC device.

    Attributes:
        mac_address: Device MAC address (on macOS, this is a UUID)
        name: Device name from BLE advertisement
        rssi: Signal strength (RSSI)
        device: The BLEDevice object for direct connection (avoids re-scanning)
    """

    mac_address: str
    name: str
    rssi: int
    device: "BLEDevice"


async def discover_atc_devices(timeout: float = 30.0) -> list[DiscoveredDevice]:
    """Discover ATC BLE devices by manufacturer ID.

    Scans for BLE devices advertising with the ATC manufacturer ID (0x1337).
    Deduplicates devices by MAC address, keeping the strongest RSSI signal.

    Args:
        timeout: Discovery timeout in seconds (default: 10.0)

    Returns:
        List of discovered ATC devices (deduplicated by MAC address)

    Example:
        >>> devices = await discover_atc_devices(timeout=5.0)
        >>> for device in devices:
        ...     print(f"Found {device.name} at {device.mac_address}")
    """
    discovered: dict[str, DiscoveredDevice] = {}

    def detection_callback(device: "BLEDevice", advertisement_data: "AdvertisementData") -> None:
        """Handle discovered BLE device."""
        mfg_data = advertisement_data.manufacturer_data
        if MANUFACTURER_ID in mfg_data:
            mac = device.address

            # Update if first time seeing this device, or if RSSI is stronger
            if mac not in discovered or advertisement_data.rssi > discovered[mac].rssi:
                _LOGGER.debug(
                    "Found ATC device: %s (%s) RSSI: %d",
                    device.name or "Unknown",
                    mac,
                    advertisement_data.rssi,
                )
                discovered[mac] = DiscoveredDevice(
                    mac_address=mac,
                    name=device.name or "Unknown",
                    rssi=advertisement_data.rssi,
                    device=device,
                )

    _LOGGER.info("Scanning for ATC devices for %ss...", timeout)
    scanner = BleakScanner(detection_callback=detection_callback)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()

    devices = list(discovered.values())
    _LOGGER.info("Discovery complete. Found %d ATC device(s)", len(devices))
    return devices
