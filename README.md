[![Tests](https://github.com/OpenDisplay-org/py-atc-ble-oepl/actions/workflows/test.yml/badge.svg)](https://github.com/OpenDisplay-org/py-atc-ble-oepl/actions/workflows/test.yml)
[![PyPI](https://img.shields.io/pypi/v/py-atc-ble-oepl)](https://pypi.org/project/py-atc-ble-oepl/)
[![Python Version](https://img.shields.io/pypi/pyversions/py-atc-ble-oepl)](https://pypi.org/project/py-atc-ble-oepl/)

# py-atc-ble-oepl

Python library for interacting with [ATC BLE firmware](https://atc1441.github.io/ATC_GICISKY_Paper_Image_Upload.html) over Bluetooth Low Energy.

## Installation

```bash
uv add py-atc-ble-oepl
```

For the CLI:

```bash
uv add "py-atc-ble-oepl[cli]"
```

Or run the CLI directly without installing into a project:

```bash
uvx --from "py-atc-ble-oepl[cli]" atc-ble scan
```

## CLI

```
atc-ble scan [--timeout 30] [--json]
atc-ble info  --device ADDR [--timeout 60] [--json]
atc-ble upload --device ADDR IMAGE [--dither-mode burkes] [--fit contain] [--rotate 0] [--no-compress]
```

**Scan for nearby devices:**
```
$ atc-ble scan
┌──────────────────────────────────────┬───────────────┬──────────┐
│ Address                              │ Name          │     RSSI │
├──────────────────────────────────────┼───────────────┼──────────┤
│ 5F4CEF52-A1CD-E2EE-011F-F27129B8D4A9 │ ATC_911943    │  -61 dBm │
└──────────────────────────────────────┴───────────────┴──────────┘
```

**Show device info:**
```
$ atc-ble info --device 5F4CEF52-A1CD-E2EE-011F-F27129B8D4A9
5F4CEF52-A1CD-E2EE-011F-F27129B8D4A9
├── Display
│   ├── Resolution    184 × 384
│   └── Color         BWY
└── Hardware
    ├── OEPL type     0x0060
    ├── Screen type   2  (350 HS BWY UC Inverted)
    └── ...
```

**Upload an image:**
```
$ atc-ble upload --device 5F4CEF52-... photo.jpg
Upload complete.
```

ATC tags advertise infrequently — the default `--timeout` for device commands is 60 s. On macOS the address is a UUID, not a MAC address.

## Python API

### Discover devices

```python
from py_atc_ble_oepl import discover_atc_devices

devices = await discover_atc_devices(timeout=30.0)
for d in devices:
    print(f"{d.name}  {d.mac_address}  {d.rssi} dBm")
```

### Upload an image

```python
from py_atc_ble_oepl import ATCDevice

async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    success = await device.upload_image("photo.jpg")
```

`upload_image` accepts a file path (`str`), raw bytes, or a PIL `Image`. It automatically:
- queries device capabilities (dimensions, color scheme)
- resizes and fits the image
- dithers to the display's color palette (MONO / BWR / BWY / BWRY)
- compresses and uploads over BLE

### Image options

```python
from py_atc_ble_oepl import ATCDevice, FitMode, Rotation
from epaper_dithering import DitherMode

async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    await device.upload_image(
        "photo.jpg",
        dither_mode=DitherMode.BURKES,   # default
        fit=FitMode.COVER,               # STRETCH / CONTAIN / COVER / CROP
        rotate=Rotation.ROTATE_90,       # 0 / 90 / 180 / 270
        compress=True,                   # default
    )
```

### Read device info

```python
from py_atc_ble_oepl import ATCDevice

async with ATCDevice("AA:BB:CC:DD:EE:FF") as device:
    caps = device._capabilities        # DeviceCapabilities
    cfg  = device.device_config        # DeviceConfig (full hardware settings)
    print(f"{caps.width}x{caps.height}  {caps.color_scheme}")
    print(f"OEPL type 0x{cfg.hw_type:04X}  screen_type {cfg.screen_type}")
```

### Pass a discovered device to avoid re-scanning

On macOS bleak can only connect to a device it has already seen during a scan. Passing the `BLEDevice` object from discovery skips a second scan:

```python
from py_atc_ble_oepl import discover_atc_devices, ATCDevice

devices = await discover_atc_devices(timeout=30.0)
if devices:
    async with ATCDevice(devices[0].mac_address, ble_device=devices[0].ble_device) as device:
        await device.upload_image("photo.jpg")
```

## API reference

### `ATCDevice`

```python
ATCDevice(mac_address, ble_device=None, auto_interrogate=True, connection_timeout=60.0)
```

| Method / Property | Description |
|---|---|
| `async interrogate()` | Query device capabilities (called automatically on connect) |
| `async upload_image(image, ...)` | Upload and display an image |
| `width`, `height` | Display dimensions in pixels (`None` before interrogation) |
| `color_scheme` | `ColorScheme` enum value (`None` before interrogation) |
| `device_config` | `DeviceConfig` dataclass with full hardware settings |

### `discover_atc_devices(timeout=30.0)`

Scans for ATC BLE devices (manufacturer ID `0x1337`). Returns `list[DiscoveredDevice]`.

### `DeviceCapabilities`

| Field | Type | Description |
|---|---|---|
| `width` | `int` | Display width in pixels |
| `height` | `int` | Display height in pixels |
| `color_scheme` | `int` | 0=MONO, 1=BWR, 2=BWY, 3=BWRY |

### `DeviceConfig`

Full hardware configuration from the `0011` dynamic config read. Key fields:

| Field | Type | Description |
|---|---|---|
| `hw_type` | `int` | OEPL tag type (hex) |
| `screen_type` | `int` | ATC screen driver type (1–47) |
| `screen_w`, `screen_h` | `int` | Physical display dimensions |
| `screen_colors` | `int` | Color count |
| `black_invert`, `second_color_invert` | `bool` | Color plane polarity |
| `epd_pinout`, `led_pinout`, `nfc_pinout`, `flash_pinout` | dataclass or `None` | GPIO pin assignments |

## Development

```bash
git clone https://github.com/OpenDisplay-org/py-atc-ble-oepl.git
cd py-atc-ble-oepl
uv sync --all-extras

uv run pytest tests/ -v
uv run ruff check .
uv run mypy src/py_atc_ble_oepl
```
