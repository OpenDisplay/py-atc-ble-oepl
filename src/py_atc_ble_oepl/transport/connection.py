"""BLE connection management using pure Bleak."""

import asyncio
import logging
from typing import TYPE_CHECKING

from bleak import BleakClient, BleakScanner
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from ..exceptions import BLEConnectionError, BLEProtocolError, BLETimeoutError

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

    from ..protocol.atc import ATCProtocol

_LOGGER = logging.getLogger(__name__)


class BLEConnection:
    """Context manager for BLE connections with protocol-specific service UUID.

    Manages BLE connection lifecycle including:
    - Connection establishment with retry logic via bleak-retry-connector
    - Service/characteristic resolution
    - Notification handling
    - Protocol initialization
    - Graceful disconnection

    Features:
    - Automatic retry logic with exponential backoff
    - Service caching for faster reconnections
    - Notification queue for response handling
    """

    def __init__(
        self,
        mac_address: str,
        service_uuid: str,
        protocol: "ATCProtocol | None" = None,
        ble_device: "BLEDevice | None" = None,
        timeout: float = 15.0,
        max_attempts: int = 4,
        use_services_cache: bool = True,
    ):
        """Initialize BLE connection manager.

        Args:
            mac_address: Device MAC address (on macOS, this is a UUID)
            service_uuid: Protocol-specific BLE service UUID
            protocol: Protocol instance for initialization (optional)
            ble_device: Optional BLEDevice from discovery (avoids re-scanning, recommended on macOS)
            timeout: Connection timeout in seconds (default: 15)
            max_attempts: Maximum connection attempts (default: 4)
            use_services_cache: Enable GATT service caching (default: True)
        """
        self.mac_address = mac_address
        self.service_uuid = service_uuid
        self.protocol = protocol
        self.ble_device = ble_device
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.use_services_cache = use_services_cache

        self.client: BleakClient | None = None
        self.write_char = None
        self._response_queue: asyncio.Queue[bytes] = asyncio.Queue()
        self._notification_active = False

    async def __aenter__(self) -> "BLEConnection":
        """Establish BLE connection and initialize protocol."""
        try:
            # Discover device by MAC address
            device = await self._discover_device()
            if not device:
                raise BLEConnectionError(f"BLE device not found: {self.mac_address}")

            # Establish connection with retry logic and service caching
            _LOGGER.debug(
                "Connecting to %s with bleak-retry-connector (max_attempts=%d)",
                self.mac_address,
                self.max_attempts,
            )

            self.client = await establish_connection(
                BleakClientWithServiceCache,
                device,
                f"ATC-{self.mac_address}",
                self._disconnected_callback,
                timeout=self.timeout,
                max_attempts=self.max_attempts,
                use_services_cache=self.use_services_cache,
            )

            # Resolve protocol-specific service characteristic
            if not self._resolve_characteristic():
                await self.client.disconnect()
                raise BLEConnectionError(f"Service {self.service_uuid} not found on {self.mac_address}")

            # Enable notifications for protocol responses
            await self.client.start_notify(self.write_char, self._notification_callback)
            self._notification_active = True

            # Let protocol handle its own initialization requirements
            if self.protocol:
                await self.protocol.initialize_connection(self)

            return self

        except BleakError as e:
            await self._cleanup()
            raise BLEConnectionError(f"BLE connection failed for {self.mac_address}: {e}") from e

        except asyncio.TimeoutError as e:
            await self._cleanup()
            raise BLETimeoutError(f"Connection timeout for {self.mac_address}") from e

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up BLE connection."""
        await self._cleanup()

    async def _discover_device(self) -> "BLEDevice | None":
        """Discover device by MAC address using BleakScanner.

        If ble_device was provided during initialization, returns it directly.
        Otherwise, performs a new scan to find the device.

        Returns:
            BLEDevice if found, None otherwise
        """
        # Use provided BLEDevice if available (avoids re-scanning on macOS)
        if self.ble_device:
            _LOGGER.debug("Using provided BLEDevice for %s", self.mac_address)
            return self.ble_device

        _LOGGER.debug("Scanning for device %s...", self.mac_address)

        device = await BleakScanner.find_device_by_address(
            self.mac_address,
            timeout=self.timeout,
        )

        if device:
            _LOGGER.debug("Found device %s", self.mac_address)
        else:
            _LOGGER.warning("Device %s not found during scan", self.mac_address)

        return device

    async def _cleanup(self):
        """Clean up connection resources."""
        if self.client and self.client.is_connected:
            if self._notification_active and self.write_char:
                try:
                    await self.client.stop_notify(self.write_char)
                except Exception:
                    _LOGGER.debug("Failed to stop notifications during cleanup")
                finally:
                    self._notification_active = False
            try:
                await self.client.disconnect()
            except Exception:
                _LOGGER.debug("Failed to disconnect during cleanup")

    def _resolve_characteristic(self) -> bool:
        """Resolve BLE characteristic for the protocol-specific service.

        Returns:
            True if characteristic was resolved successfully, False otherwise
        """
        try:
            if not self.client or not self.client.services:
                return False

            # Find the protocol-specific service characteristic
            char = self.client.services.get_characteristic(self.service_uuid)
            if char:
                self.write_char = char
                _LOGGER.debug(
                    "Resolved characteristic for service %s on %s",
                    self.service_uuid,
                    self.mac_address,
                )
                return True

            _LOGGER.error(
                "Could not find characteristic for service %s on %s",
                self.service_uuid,
                self.mac_address,
            )
            return False

        except Exception as e:
            _LOGGER.error("Error resolving characteristic for %s: %s", self.mac_address, e)
            return False

    def _notification_callback(self, sender, data: bytearray) -> None:
        """Handle notification from device.

        Args:
            sender: Notification sender
            data: Notification data
        """
        try:
            self._response_queue.put_nowait(bytes(data))
        except asyncio.QueueFull:
            _LOGGER.warning("Response queue full for %s, dropping notification", self.mac_address)

    async def _write_raw(self, data: bytes) -> None:
        """Write raw data to device characteristic.

        Args:
            data: Raw bytes to write

        Raises:
            BLEProtocolError: If write characteristic is not available
        """
        if not self.write_char:
            raise BLEProtocolError("Write characteristic not available")

        await self.client.write_gatt_char(self.write_char, data, response=False)

    async def write_command_with_response(self, command: bytes, timeout: float = 10.0) -> bytes:
        """Write command and wait for response.

        Args:
            command: Command bytes to write
            timeout: Response timeout in seconds (default: 10)

        Returns:
            Response data from device

        Raises:
            BLETimeoutError: If no response received within timeout
        """
        # Clear any pending responses
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        await self._write_raw(command)

        try:
            response = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            raise BLETimeoutError(f"No response received from {self.mac_address} within {timeout}s") from None

    async def write_command(self, data: bytes) -> None:
        """Write command to device without expecting response.

        Args:
            data: Command bytes to write
        """
        await self._write_raw(data)

    async def read_response(self, timeout: float = 10.0) -> bytes:
        """Read next response from notification queue without clearing.

        Used for protocols that expect multiple responses per command.

        Args:
            timeout: Response timeout in seconds (default: 10)

        Returns:
            Response data from device

        Raises:
            BLETimeoutError: If no response received within timeout
        """
        try:
            response = await asyncio.wait_for(self._response_queue.get(), timeout=timeout)
            return response
        except asyncio.TimeoutError:
            raise BLETimeoutError(f"No response received from {self.mac_address} within {timeout}s") from None

    def _disconnected_callback(self, client: BleakClient) -> None:
        """Handle disconnection event.

        Args:
            client: Disconnected BleakClient
        """
        _LOGGER.debug("Device %s disconnected", self.mac_address)
