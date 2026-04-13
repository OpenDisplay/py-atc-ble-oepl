"""Command-line interface for py-atc-ble-oepl."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from collections.abc import Coroutine
from dataclasses import asdict
from typing import Any, NoReturn, TypeVar

from epaper_dithering import DitherMode
from PIL import Image, UnidentifiedImageError
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.tree import Tree

from .device import ATCDevice
from .discovery import discover_atc_devices
from .exceptions import ATCError, BLEConnectionError, BLEProtocolError, BLETimeoutError
from .models.device_types import get_device_type_name
from .models.enums import FitMode, Rotation

_T = TypeVar("_T")

_console = Console(stderr=True)  # status, spinners, tables, errors → stderr
_stdout = Console()               # structured data (--json output) → stdout

_DITHER_CHOICES: dict[str, DitherMode] = {m.name.lower().replace("_", "-"): m for m in DitherMode}
_FIT_CHOICES: dict[str, FitMode] = {m.name.lower(): m for m in FitMode}
_ROTATE_CHOICES: dict[str, Rotation] = {
    "0": Rotation.ROTATE_0,
    "90": Rotation.ROTATE_90,
    "180": Rotation.ROTATE_180,
    "270": Rotation.ROTATE_270,
}

_COLOR_SCHEME_NAMES = {0: "MONO", 1: "BWR", 2: "BWY", 3: "BWRY", 4: "BWGBRY", 5: "GRAY4"}


def _run(coro: Coroutine[Any, Any, _T]) -> _T:
    return asyncio.run(coro)


def _error(msg: str) -> NoReturn:
    _console.print(f"[bold red]Error:[/bold red] {msg}")
    sys.exit(1)


def _handle_ble_error(exc: Exception) -> NoReturn:
    if isinstance(exc, BLETimeoutError):
        _error(f"BLE timeout: {exc}")
    if isinstance(exc, BLEConnectionError):
        _error(f"BLE connection failed: {exc}")
    if isinstance(exc, BLEProtocolError):
        _error(f"Protocol error: {exc}")
    if isinstance(exc, ATCError):
        _error(f"Device error: {exc}")
    _error(str(exc))


def _spinner() -> Progress:
    return Progress(SpinnerColumn(), TextColumn("{task.description}"), transient=True, console=_console)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=_console, rich_tracebacks=True)],
        force=True,
    )
    logging.getLogger("bleak").setLevel(logging.INFO)


def _add_device_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--device", required=True, metavar="ADDR", help="Device MAC address or UUID")
    parser.add_argument(
        "--timeout", type=float, default=60.0, metavar="SECS", help="BLE timeout in seconds (default: 60.0)"
    )


# ── scan ──────────────────────────────────────────────────────────────────────


def _add_scan_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("scan", help="Discover nearby ATC BLE devices")
    p.add_argument(
        "--timeout", type=float, default=30.0, metavar="SECS", help="Scan duration in seconds (default: 30.0)"
    )
    p.add_argument("--json", dest="output_json", action="store_true", help="Output results as JSON")
    p.set_defaults(func=_cmd_scan)


def _cmd_scan(args: argparse.Namespace) -> None:
    _run(_scan(args.timeout, args.output_json))


async def _scan(timeout: float, output_json: bool) -> None:
    with _spinner() as progress:
        progress.add_task(f"Scanning for {timeout:.0f}s…", total=None)
        devices = await discover_atc_devices(timeout=timeout)

    if output_json:
        _stdout.print_json(json.dumps([{"address": d.mac_address, "name": d.name, "rssi": d.rssi} for d in devices]))
        return

    if not devices:
        _console.print("No ATC devices found.")
        return

    table = Table(show_header=True)
    table.add_column("Address", style="cyan")
    table.add_column("Name")
    table.add_column("RSSI", justify="right")
    for d in devices:
        table.add_row(d.mac_address, d.name, f"{d.rssi} dBm")
    _console.print(table)


# ── info ──────────────────────────────────────────────────────────────────────


def _add_info_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("info", help="Read and display device information")
    _add_device_options(p)
    p.add_argument("--json", dest="output_json", action="store_true", help="Output as JSON")
    p.set_defaults(func=_cmd_info)


def _cmd_info(args: argparse.Namespace) -> None:
    _run(_info(args.device, args.timeout, args.output_json))


async def _info(address: str, timeout: float, output_json: bool) -> None:
    try:
        with _spinner() as progress:
            task = progress.add_task("Connecting…", total=None)
            async with ATCDevice(address, connection_timeout=timeout) as device:
                progress.update(task, description="Reading info…")
                caps = device._capabilities
                config = device.device_config
    except (ATCError, BLEConnectionError, BLETimeoutError, BLEProtocolError) as exc:
        _handle_ble_error(exc)

    if output_json:
        out: dict[str, Any] = {}
        if caps:
            out["capabilities"] = {
                "width": caps.width,
                "height": caps.height,
                "color_scheme": caps.color_scheme,
                "rotatebuffer": caps.rotatebuffer,
            }
        if config:
            out["config"] = asdict(config)
        _stdout.print_json(json.dumps(out))
        return

    tree = Tree(f"[bold cyan]{address}[/bold cyan]", guide_style="cyan dim")

    if caps:
        color_name = _COLOR_SCHEME_NAMES.get(caps.color_scheme, str(caps.color_scheme))
        disp = tree.add("[bold]Display[/bold]")
        disp.add(f"Resolution    {caps.width} × {caps.height}")
        disp.add(f"Color         {color_name}")
        disp.add(f"Rotate buffer {caps.rotatebuffer}")

    if config:
        screen_type_name = get_device_type_name(config.screen_type)
        hw = tree.add("[bold]Hardware[/bold]")
        hw.add(f"OEPL type     [yellow]0x{config.hw_type:04X}[/yellow]")
        hw.add(f"Screen type   [yellow]{config.screen_type}[/yellow]  ({screen_type_name})")
        hw.add(f"Functions     0x{config.screen_functions:04X}")
        hw.add(f"WH inv (BLE)  {config.wh_inverted_ble}   WH inv (cfg)  {config.wh_inverted}")
        hw.add(f"Offsets       H={config.screen_h_offset}  W={config.screen_w_offset}")
        hw.add(
            f"Colors        {config.screen_colors}  "
            f"black_invert={config.black_invert}  "
            f"color_invert={config.second_color_invert}"
        )
        hw.add(f"ADC pinout    0x{config.adc_pinout:04X}   UART pinout   0x{config.uart_pinout:04X}")

        for label, enabled, pinout in [
            ("EPD", config.epd_enabled, config.epd_pinout),
            ("LED", config.led_enabled, config.led_pinout),
            ("NFC", config.nfc_enabled, config.nfc_pinout),
            ("Flash", config.flash_enabled, config.flash_pinout),
        ]:
            if not enabled:
                hw.add(f"{label}           [dim]disabled[/dim]")
            else:
                branch = hw.add(f"{label}           [green]enabled[/green]")
                if pinout:
                    for k, v in asdict(pinout).items():  # type: ignore[arg-type]
                        branch.add(f"{k}: {v}")

    _console.print(tree)


# ── upload ────────────────────────────────────────────────────────────────────


def _add_upload_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = subparsers.add_parser("upload", help="Upload an image to the device")
    _add_device_options(p)
    p.add_argument("image", metavar="IMAGE_PATH", help="Path to the image file")
    p.add_argument(
        "--dither-mode",
        choices=list(_DITHER_CHOICES),
        default="ordered",
        help="Dithering algorithm (default: ordered)",
    )
    p.add_argument(
        "--fit",
        choices=list(_FIT_CHOICES),
        default="contain",
        help="Image fit strategy (default: contain)",
    )
    p.add_argument(
        "--rotate",
        choices=list(_ROTATE_CHOICES),
        default="0",
        help="Additional image rotation in degrees on top of device rotation (default: 0)",
    )
    p.add_argument("--no-compress", action="store_true", help="Disable zlib compression")
    p.set_defaults(func=_cmd_upload)


def _cmd_upload(args: argparse.Namespace) -> None:
    _run(
        _upload(
            args.device,
            args.timeout,
            args.image,
            _DITHER_CHOICES[args.dither_mode],
            _FIT_CHOICES[args.fit],
            _ROTATE_CHOICES[args.rotate],
            not args.no_compress,
        )
    )


async def _upload(
    address: str,
    timeout: float,
    image_path: str,
    dither_mode: DitherMode,
    fit: FitMode,
    rotate: Rotation,
    compress: bool,
) -> None:
    try:
        image = Image.open(image_path)
    except FileNotFoundError:
        _error(f"Image file not found: {image_path}")
    except UnidentifiedImageError:
        _error(f"Cannot open image (unsupported format): {image_path}")

    try:
        with _spinner() as progress:
            task = progress.add_task("Connecting…", total=None)
            async with ATCDevice(address, connection_timeout=timeout) as device:
                progress.update(task, description="Uploading…")
                success = await device.upload_image(
                    image,
                    dither_mode=dither_mode,
                    compress=compress,
                    fit=fit,
                    rotate=rotate,
                )
    except (ATCError, BLEConnectionError, BLETimeoutError, BLEProtocolError) as exc:
        _handle_ble_error(exc)

    if success:
        _console.print("Upload complete.")
    else:
        _error("Upload failed.")


# ── entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="atc-ble",
        description="ATC BLE e-paper display command-line tool",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_scan_parser(subparsers)
    _add_info_parser(subparsers)
    _add_upload_parser(subparsers)

    args = parser.parse_args()
    _setup_logging(args.verbose)
    args.func(args)


if __name__ == "__main__":
    main()
