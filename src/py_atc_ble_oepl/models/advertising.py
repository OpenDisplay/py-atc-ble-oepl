"""BLE advertising data model."""

from dataclasses import dataclass


@dataclass
class AdvertisingData:
    """Parsed BLE advertising data from ATC devices.

    Attributes:
        battery_mv: Battery voltage in millivolts
        battery_pct: Battery percentage (0-100)
        temperature: Temperature in Celsius (None for version 1)
        hw_type: Hardware type identifier
        fw_version: Firmware version number
        version: Advertising data format version (1 or 2)
    """

    battery_mv: int
    battery_pct: int
    temperature: int | None
    hw_type: int
    fw_version: int
    version: int
