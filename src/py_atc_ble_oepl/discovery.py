"""BLE device discovery for ATC tags."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bleak import BleakScanner

from .models.advertising import AdvertisingData
from .protocol.atc import ATCProtocol
from .protocol.constants import MANUFACTURER_ID

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)


@dataclass
class DiscoveredDevice:
    """Information about a discovered ATC device.

    Attributes:
        mac_address: Device MAC address (on macOS, this is a UUID)
        name: Device name from BLE advertisement
        rssi: Signal strength (RSSI)
        device: The BLEDevice object for direct connection (avoids re-scanning)
        advertising_data: Parsed ATC advertising payload (battery, fw version, temp)
    """

    mac_address: str
    name: str
    rssi: int
    device: BLEDevice
    advertising_data: AdvertisingData | None = field(default=None)


async def discover_atc_devices(timeout: float = 30.0) -> list[DiscoveredDevice]:
    """Discover ATC BLE devices by manufacturer ID.

    Scans for BLE devices advertising with the ATC manufacturer ID (0x1337).

    Args:
        timeout: Discovery timeout in seconds (default: 30.0)

    Returns:
        List of discovered ATC devices

    Example:
        >>> devices = await discover_atc_devices(timeout=5.0)
        >>> for device in devices:
        ...     print(f"Found {device.name} at {device.mac_address}")
    """
    _LOGGER.info("Scanning for ATC devices for %ss...", timeout)
    raw = await BleakScanner.discover(timeout=timeout, return_adv=True)

    _protocol = ATCProtocol()
    result: list[DiscoveredDevice] = []

    for device, adv_data in raw.values():
        if MANUFACTURER_ID not in adv_data.manufacturer_data:
            continue

        adv: AdvertisingData | None = None
        try:
            adv = _protocol.parse_advertising_data(adv_data.manufacturer_data[MANUFACTURER_ID])
        except ValueError:
            _LOGGER.debug("Failed to parse advertising data for %s", device.address)

        _LOGGER.debug(
            "Found ATC device: %s (%s) RSSI: %d",
            device.name or "Unknown",
            device.address,
            adv_data.rssi,
        )
        result.append(
            DiscoveredDevice(
                mac_address=device.address,
                name=device.name or "Unknown",
                rssi=adv_data.rssi,
                device=device,
                advertising_data=adv,
            )
        )

    _LOGGER.info("Discovery complete. Found %d ATC device(s)", len(result))
    return result
