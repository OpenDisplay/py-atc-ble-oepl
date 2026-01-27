# py-atc-ble-oepl

Python module for interacting with ATC BLE firmware on OEPL e-paper tags

[![Tests](https://github.com/OpenDisplay-org/py-atc-ble-oepl/actions/workflows/test.yml/badge.svg)](https://github.com/OpenDisplay-org/py-atc-ble-oepl/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/py-atc-ble-oepl)](https://pypi.org/project/py-atc-ble-oepl/)
[![Python Version](https://img.shields.io/pypi/pyversions/py-atc-ble-oepl)](https://pypi.org/project/py-atc-ble-oepl/)

## Installation

```bash
pip install py-atc-ble-oepl
```

## Features

- **Device Discovery** - Find ATC BLE devices by manufacturer ID
- **Image Upload** - Upload images to e-paper displays with automatic dithering
- **Color Support** - Monochrome, BWR, BWY, and BWRY color schemes
- **Automatic Rotation** - Handles 90° rotation for ATC devices
- **Compression** - Optional zlib compression for faster transfers
- **Async API** - Built with asyncio for efficient BLE communication

## Quick Start

### Discover Devices

```python
from py_atc_ble_oepl import discover_atc_devices

# Find all ATC devices
devices = await discover_atc_devices(timeout=5.0)
for device in devices:
    print(f"Found {device.name} at {device.mac_address}")
```

### Upload Image

```python
from py_atc_ble_oepl import ATCDevice
from epaper_dithering import DitherMode

# Upload with auto-interrogation
async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    await device.upload_image("photo.jpg")

# Custom dithering
async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    await device.upload_image(
        "photo.jpg",
        dither_mode=DitherMode.BURKES,
        compress=True
    )
```

## Usage

### Device Information

```python
from py_atc_ble_oepl import ATCDevice

device = ATCDevice("AA:BB:CC:DD:EE:FF")
caps = await device.interrogate()
print(f"Display: {caps.width}x{caps.height}")
print(f"Color scheme: {caps.color_scheme}")
```

### Advanced: Manual Workflow

```python
from py_atc_ble_oepl import ATCDevice
from PIL import Image
from epaper_dithering import ColorScheme, DitherMode, dither_image

# Create device without auto-interrogation
device = ATCDevice("AA:BB:CC:DD:EE:FF", auto_interrogate=False)

# Query device capabilities
caps = await device.interrogate()

# Prepare image manually
img = Image.open("photo.jpg").resize((caps.width, caps.height))
dithered = dither_image(img, ColorScheme(caps.color_scheme), DitherMode.BURKES)

# Upload
await device.upload_image(dithered, compress=True)
```

## API Reference

### ATCDevice

Main class for interacting with ATC BLE devices.

**Constructor:**
```python
ATCDevice(mac_address, auto_interrogate=True, connection_timeout=15.0)
```

**Methods:**
- `interrogate()` → `DeviceCapabilities` - Query device capabilities
- `upload_image(image, dither_mode=DitherMode.ORDERED, compress=True)` → `bool` - Upload image

**Properties:**
- `width` → `int | None` - Display width in pixels
- `height` → `int | None` - Display height in pixels
- `color_scheme` → `ColorScheme | None` - Display color scheme
- `rotatebuffer` → `int | None` - Rotation flag (1=rotate 90°)

### discover_atc_devices(timeout=10.0)

Discover ATC BLE devices.

**Returns:** `list[DiscoveredDevice]` - List of discovered devices

**Example:**
```python
devices = await discover_atc_devices(timeout=5.0)
```

## Development

### Setup

```bash
# Clone the repository
git clone https://github.com/OpenDisplay-org/py-atc-ble-oepl.git
cd py-atc-ble-oepl

# Install with all dependencies
uv sync --all-extras
```

### Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=src/py_atc_ble_oepl

# Run specific test file
uv run pytest tests/test_specific.py -v
```

### Code Quality

```bash
# Lint code
uv run ruff check .

# Format code (if ruff format is configured)
uv run ruff format .

# Type check
uv run mypy src/py_atc_ble_oepl
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests and linting
5. Commit using conventional commits (`feat:`, `fix:`, etc.)
6. Push to your fork
7. Open a Pull Request
