"""Main ATC BLE device class."""

import asyncio
import io
import logging
from typing import TYPE_CHECKING

from epaper_dithering import ColorScheme, DitherMode, dither_image
from PIL import Image

from .exceptions import ATCError
from .imaging.uploader import BLEImageUploader
from .models.capabilities import DeviceCapabilities
from .models.device_config import DeviceConfig
from .models.device_types import SCREEN_TYPE_COLOR_SCHEME
from .models.enums import FitMode, Rotation
from .models.metadata import DeviceMetadata
from .protocol.atc import ATCProtocol
from .protocol.constants import SERVICE_UUID
from .transport.connection import BLEConnection

if TYPE_CHECKING:
    from bleak.backends.device import BLEDevice

_LOGGER = logging.getLogger(__name__)

_TRANSPOSE_MAP = {
    Rotation.ROTATE_90: Image.Transpose.ROTATE_90,
    Rotation.ROTATE_180: Image.Transpose.ROTATE_180,
    Rotation.ROTATE_270: Image.Transpose.ROTATE_270,
}


def _apply_image_transform(img: Image.Image, rotate: Rotation, fit: FitMode, w: int, h: int) -> Image.Image:
    """Apply user rotation then fit/resize to target dimensions.

    Args:
        img: Source PIL Image
        rotate: User-requested rotation (applied before fit)
        fit: How to map image to target dimensions
        w: Target width in pixels
        h: Target height in pixels

    Returns:
        Transformed PIL Image at exactly (w, h) pixels
    """
    # Step 1 — user rotation
    if rotate != Rotation.ROTATE_0:
        img = img.transpose(_TRANSPOSE_MAP[rotate])

    # Step 2 — fit to (w, h)
    img = img.convert("RGB")

    if fit == FitMode.STRETCH:
        return img.resize((w, h), Image.Resampling.LANCZOS)

    if fit == FitMode.CONTAIN:
        img.thumbnail((w, h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (w, h), (255, 255, 255))
        paste_x = (w - img.width) // 2
        paste_y = (h - img.height) // 2
        canvas.paste(img, (paste_x, paste_y))
        return canvas

    if fit == FitMode.COVER:
        scale = max(w / img.width, h / img.height)
        new_w = int(img.width * scale)
        new_h = int(img.height * scale)
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        left = (new_w - w) // 2
        top = (new_h - h) // 2
        return img.crop((left, top, left + w, top + h))

    # FitMode.CROP — center-crop at native resolution, pad with white if smaller
    canvas = Image.new("RGB", (w, h), (255, 255, 255))
    paste_x = (w - img.width) // 2
    paste_y = (h - img.height) // 2
    # Crop source if larger than target
    src_x = max(0, -paste_x)
    src_y = max(0, -paste_y)
    src_w = min(img.width, w)
    src_h = min(img.height, h)
    dest_x = max(0, paste_x)
    dest_y = max(0, paste_y)
    canvas.paste(img.crop((src_x, src_y, src_x + src_w, src_y + src_h)), (dest_x, dest_y))
    return canvas


class ATCDevice:
    """ATC BLE e-paper display device.

    Main API for communicating with ATC BLE e-paper tags.

    Usage:
        Basic usage with auto-interrogation:
        ```python
        async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
            await device.upload_image("image.jpg")
        ```

        Manual interrogation:
        ```python
        device = ATCDevice("AA:BB:CC:DD:EE:FF", auto_interrogate=False)
        caps = await device.interrogate()
        print(f"Display: {caps.width}x{caps.height}")
        await device.upload_image("image.jpg")
        ```

        Custom dithering:
        ```python
        from epaper_dithering import DitherMode

        async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
            await device.upload_image(
                "image.jpg",
                dither_mode=DitherMode.BURKES,
                compress=True
            )
        ```
    """

    def __init__(
        self,
        mac_address: str,
        ble_device: "BLEDevice | None" = None,
        auto_interrogate: bool = True,
        connection_timeout: float = 15.0,
    ):
        """Initialize ATC device.

        Args:
            mac_address: Device MAC address (on macOS, this is a UUID)
            ble_device: Optional BLEDevice from discovery (avoids re-scanning, recommended on macOS)
            auto_interrogate: Automatically query device capabilities on first connection
            connection_timeout: BLE connection timeout in seconds (default: 15.0)
        """
        self.mac_address = mac_address
        self._ble_device = ble_device
        self._auto_interrogate = auto_interrogate
        self._timeout = connection_timeout
        self._capabilities: DeviceCapabilities | None = None
        self._device_config: DeviceConfig | None = None
        self._metadata: DeviceMetadata | None = None
        self._connection: BLEConnection | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "ATCDevice":
        """Context manager entry - connect and optionally auto-interrogate."""
        # Create persistent connection
        protocol = ATCProtocol()
        self._connection = BLEConnection(
            self.mac_address, SERVICE_UUID, protocol, ble_device=self._ble_device, timeout=self._timeout
        )

        # Connect to device
        await self._connection.__aenter__()

        # Auto-interrogate if enabled
        if self._auto_interrogate and not self._capabilities:
            await self.interrogate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect."""
        if self._connection:
            await self._connection.__aexit__(exc_type, exc_val, exc_tb)

    async def interrogate(self) -> DeviceCapabilities:
        """Query device capabilities.

        Retrieves display specifications including dimensions, color support,
        and rotation requirements from the connected device.

        Returns:
            DeviceCapabilities with device information

        Raises:
            RuntimeError: If not connected (call within context manager)
            BLEProtocolError: If interrogation fails
            BLETimeoutError: If operation times out

        Example:
            >>> async with ATCDevice("AA:BB:CC:DD:EE:FF", auto_interrogate=False) as device:
            ...     caps = await device.interrogate()
            ...     print(f"{caps.width}x{caps.height}, colors: {caps.color_scheme}")
        """
        if not self._connection:
            raise RuntimeError("Not connected - use device within async context manager")

        async with self._lock:
            # Query display info and dynamic config using persistent connection
            protocol = self._connection.protocol
            self._capabilities = await protocol.interrogate_device(self._connection)
            self._device_config = await protocol.read_device_config(self._connection)

            # Refine color_scheme using screen_type from dynamic config.
            # The 0005 response only gives a color count (1/2/3) and cannot
            # distinguish BWR from BWY; screen_type encodes that information.
            refined = SCREEN_TYPE_COLOR_SCHEME.get(self._device_config.screen_type)
            if refined is not None:
                self._capabilities = DeviceCapabilities(
                    width=self._capabilities.width,
                    height=self._capabilities.height,
                    color_scheme=refined,
                    rotatebuffer=self._capabilities.rotatebuffer,
                )
                _LOGGER.debug(
                    "Refined color_scheme from 0005 value to %d via screen_type %d",
                    refined,
                    self._device_config.screen_type,
                )

            # Build metadata for image processing
            self._metadata = DeviceMetadata(
                {
                    "width": self._capabilities.width,
                    "height": self._capabilities.height,
                    "color_scheme": self._capabilities.color_scheme,
                    "rotatebuffer": self._capabilities.rotatebuffer,
                }
            )

            _LOGGER.info(
                "Interrogated device %s: %dx%d, color_scheme=%d, rotate=%d",
                self.mac_address,
                self._capabilities.width,
                self._capabilities.height,
                self._capabilities.color_scheme,
                self._capabilities.rotatebuffer,
            )

            return self._capabilities

    async def upload_image(
        self,
        image_data: bytes | str | Image.Image,
        dither_mode: DitherMode = DitherMode.BURKES,
        compress: bool = True,
        fit: FitMode = FitMode.CONTAIN,
        rotate: Rotation = Rotation.ROTATE_0,
    ) -> bool:
        """Upload image to device display.

        Automatically handles:
        - Image loading from various formats
        - Resizing to display dimensions
        - Dithering based on color scheme
        - Encoding to device format
        - Optional compression
        - Block-based BLE upload protocol

        Args:
            image_data: Image as bytes (JPEG/PNG), file path (str), or PIL Image
            dither_mode: Dithering algorithm (default: BAYER_8x8)
            compress: Enable zlib compression (default: True)

        Returns:
            True if upload succeeded, False otherwise

        Raises:
            ATCError: If device not interrogated and auto_interrogate=False

        Example:
            >>> async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
            ...     success = await device.upload_image("photo.jpg")
            ...     print(f"Upload: {'success' if success else 'failed'}")
        """
        async with self._lock:
            # Ensure capabilities known
            if not self._metadata:
                if self._auto_interrogate:
                    await self.interrogate()
                else:
                    raise ATCError("Device not interrogated. Call interrogate() first or set auto_interrogate=True")

            # Load image
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
            elif isinstance(image_data, str):
                img = Image.open(image_data)
            else:
                img = image_data

            _LOGGER.debug("Original image size: %dx%d", img.width, img.height)

            # Determine target dimensions — rotatebuffer is handled internally by the
            # ATC firmware; we encode at the logical display dimensions as reported.
            target_width = self._metadata.width
            target_height = self._metadata.height

            # Apply user rotation + fit to target dimensions
            img = _apply_image_transform(img, rotate, fit, target_width, target_height)
            _LOGGER.debug("Transformed to %dx%d for device", img.width, img.height)

            # Apply dithering using epaper_dithering
            color_scheme = ColorScheme.from_value(self._metadata.color_scheme)
            dithered = dither_image(img, color_scheme, dither_mode)
            _LOGGER.debug(
                "Applied %s dithering for color scheme %s",
                dither_mode.name,
                color_scheme.name,
            )

            # Encode and upload using persistent connection
            if not self._connection:
                raise RuntimeError("Not connected - use device within async context manager")

            uploader = BLEImageUploader(self._connection, self.mac_address)
            success = await uploader.upload_image_block_based(dithered, self._metadata.color_scheme, compress=compress)
            return success

    @property
    def width(self) -> int | None:
        """Display width in pixels (None if not interrogated)."""
        return self._capabilities.width if self._capabilities else None

    @property
    def height(self) -> int | None:
        """Display height in pixels (None if not interrogated)."""
        return self._capabilities.height if self._capabilities else None

    @property
    def color_scheme(self) -> ColorScheme | None:
        """Display color scheme (None if not interrogated)."""
        if self._capabilities:
            return ColorScheme.from_value(self._capabilities.color_scheme)
        return None

    @property
    def rotatebuffer(self) -> int | None:
        """Rotation flag: 1=rotate 90°, 0=no rotation (None if not interrogated)."""
        return self._capabilities.rotatebuffer if self._capabilities else None

    @property
    def device_config(self) -> DeviceConfig | None:
        """Full device configuration from dynamic config read (None if not interrogated)."""
        return self._device_config
