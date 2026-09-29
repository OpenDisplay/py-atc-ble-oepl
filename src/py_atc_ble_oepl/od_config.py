"""Convert an ATC tag's dynamic config (0x0011) into an OpenDisplay device config.

The result is the JSON document ``opendisplay write-config`` (py-opendisplay) accepts, so a tag
can be read while it still runs ATC_BLE_OEPL, flashed with the OpenDisplay Telink firmware
(Firmware_Unified ``targets/telink-tlsr``), and then given a config that matches its hardware.

Only what is known is written. Anything the OpenDisplay config cannot express, or that this
module cannot map with confidence, is reported in :attr:`ODConfigResult.warnings` instead of
being guessed -- a wrong pin or panel type drives real hardware wrongly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .models.device_config import DeviceConfig
from .models.device_types import DEVICE_TYPES, SCREEN_TYPE_COLOR_SCHEME

PIN_NONE = 0xFF

# OpenDisplay enum values (opendisplay-protocol, opendisplay_structs.h).
_DISPLAY_TECH_E_PAPER = 1
_POWER_MODE_BATTERY = 1
_LED_TYPE_RGB = 0
_COLOR_MONO, _COLOR_BWR, _COLOR_BWY, _COLOR_BWRY = 0, 1, 2, 3
# Direct write + zlib with the 512-byte streaming window; the Telink build has no PIPE.
_TX_MODES_TELINK = (1 << 3) | (1 << 1) | (1 << 0)


@dataclass(frozen=True)
class PanelModel:
    """One entry of the PanelIC 1000-1032 line (the EPD-nRF5 / Firmware_NRF52 models, plus 1031-1032).

    Width and height are the controller's native orientation, which is what the firmware checks
    the config against.
    """

    panel_ic: int
    name: str
    controller: str  # "SSD" or "UC" -- the ATC type-name convention
    width: int
    height: int
    colors: int  # 1 = BW, 2 = two-plane (BWR/BWY), 3 = BWRY
    # DisplayConfig.rotation index (0-3 = 0/90/180/270 deg) that makes the tag's natural face
    # upright (the way its case is held): hosts add it to the requested rotation, and the
    # firmware draws its boot screen with it.
    rotation: int = 0
    # ATC's screen_w x screen_h for this glass when it differs from the native size: ATC reports
    # the Hanshow BWY as 152x200, but it is wired 200 sources x 152 gates.
    atc_size: tuple[int, int] | None = None

    def matches_atc_size(self, w: int, h: int) -> bool:
        return (w, h) == (self.atc_size or (self.width, self.height))


# Canonical values from opendisplay_structs.h, enum PanelIC.
PANEL_MODELS: tuple[PanelModel, ...] = (
    PanelModel(1000, "UC8176_420_BW", "UC", 400, 300, 1),
    PanelModel(1001, "SSD1619_420_BWR", "SSD", 400, 300, 2),
    PanelModel(1002, "UC8176_420_BWR", "UC", 400, 300, 2),
    PanelModel(1003, "SSD1619_420_BW", "SSD", 400, 300, 1),
    PanelModel(1004, "JD79668_420_BWRY", "JD", 400, 300, 3),
    PanelModel(1005, "UC8179_750_BW", "UC", 800, 480, 1),
    PanelModel(1006, "UC8179_750_BWR", "UC", 800, 480, 2),
    PanelModel(1007, "UC8159_750_LOW_BW", "UC", 640, 384, 1),
    PanelModel(1008, "UC8159_750_LOW_BWR", "UC", 640, 384, 2),
    PanelModel(1009, "SSD1677_750_HD_BW", "SSD", 880, 528, 1),
    PanelModel(1010, "SSD1677_750_HD_BWR", "SSD", 880, 528, 2),
    PanelModel(1011, "JD79665_750_BWRY", "JD", 800, 480, 3),
    PanelModel(1012, "JD79665_583_BWRY", "JD", 648, 480, 3),
    PanelModel(1013, "UC8151_029_BW", "UC", 168, 384, 1),
    PanelModel(1014, "UC8151_029_BWR", "UC", 168, 384, 2),
    PanelModel(1015, "SSD1619_029_BW", "SSD", 168, 384, 1),
    PanelModel(1016, "SSD1619_029_BWR", "SSD", 168, 384, 2),
    PanelModel(1017, "SSD1619_016_BW", "SSD", 200, 200, 1),
    PanelModel(1018, "SSD1619_016_BWR", "SSD", 200, 200, 2),
    PanelModel(1019, "SSD1619_022_BW", "SSD", 240, 320, 1),
    PanelModel(1020, "SSD1619_022_BWR", "SSD", 240, 320, 2),
    PanelModel(1021, "SSD1619_026_BW", "SSD", 296, 152, 1),
    PanelModel(1022, "SSD1619_026_BWR", "SSD", 296, 152, 2),
    PanelModel(1023, "UC8151_027_BW", "UC", 200, 300, 1),
    PanelModel(1024, "UC8151_027_BWR", "UC", 200, 300, 2),
    PanelModel(1025, "UC43_430_BW", "UC", 152, 522, 1),
    PanelModel(1026, "UC43_430_BWR", "UC", 152, 522, 2),
    PanelModel(1027, "SSD1619_013_BW", "SSD", 144, 200, 1),
    PanelModel(1028, "SSD1619_013_BWR", "SSD", 144, 200, 2),
    PanelModel(1029, "SSD1619_022_LITE_BW", "SSD", 128, 250, 1),
    PanelModel(1030, "SSD1619_022_LITE_BWR", "SSD", 128, 250, 2),
    # Telink-target addition, provisional until opendisplay-protocol assigns it: the Hanshow 2.66"
    # on ATC tags. Same size as SSD1619_026 but transposed (152 sources x 296 gates).
    PanelModel(1031, "SSD16XX_HS_266_BWR", "SSD", 152, 296, 2, rotation=1),
    # Hanshow 2.0" BWY (ATC type 5): provisional like 1031, Telink firmware only.
    PanelModel(1032, "SSD16XX_HS_200_BWY", "SSD", 200, 152, 2, rotation=3, atc_size=(152, 200)),
)


class UnsupportedTagError(ValueError):
    """The tag's panel has no OpenDisplay equivalent, so no usable config can be produced."""


@dataclass
class ODConfigResult:
    """A converted config and everything the conversion could not carry over."""

    config_json: dict[str, Any]
    panel: PanelModel
    warnings: list[str] = field(default_factory=list)


def atc_pin_to_od(value: int) -> int:
    """Convert an ATC pin word (``port << 8 | 1 << bit``) to an OpenDisplay pin number.

    OpenDisplay numbers Telink pins ``port * 8 + bit`` (PA0 = 0, PB4 = 12, PD7 = 31); 0 means
    "not connected" in ATC and maps to 0xFF.

    Raises:
        ValueError: for a word that is not exactly one pin on ports A-E.
    """
    if value == 0:
        return PIN_NONE
    port, bits = (value >> 8) & 0xFF, value & 0xFF
    if port > 4 or bits == 0 or bits & (bits - 1):
        raise ValueError(f"not a single Telink pin: 0x{value:04X}")
    return port * 8 + bits.bit_length() - 1


def od_pin_name(pin: int) -> str:
    """``12`` -> ``"PB4"``; 0xFF -> ``"-"``."""
    return "-" if pin == PIN_NONE else f"P{'ABCDE'[pin // 8]}{pin % 8}"


def _controller_family(screen_type: int) -> str | None:
    name = DEVICE_TYPES.get(screen_type, "")
    for token in name.split():
        if token in ("SSD", "UC", "JD", "ST", "TI"):
            return token
    return None


def _color_scheme(config: DeviceConfig) -> int:
    if config.screen_type in SCREEN_TYPE_COLOR_SCHEME:
        return SCREEN_TYPE_COLOR_SCHEME[config.screen_type]
    return {1: _COLOR_MONO, 2: _COLOR_BWR, 3: _COLOR_BWRY}.get(config.screen_colors, _COLOR_MONO)


def match_panel(config: DeviceConfig) -> PanelModel:
    """Find the OpenDisplay panel model for an ATC tag, by controller family, size and colours.

    Matching is on physical facts only -- the ATC type name's controller token, the controller-
    native resolution, and the plane count -- never on the ATC type number, which has no
    OpenDisplay counterpart.

    Raises:
        UnsupportedTagError: when nothing matches.
    """
    family = _controller_family(config.screen_type)
    type_name = DEVICE_TYPES.get(config.screen_type, f"screen_type {config.screen_type}")
    # screen_w x screen_h is ATC's raw, controller-native size (sources x gates), before its own
    # host-facing swap. It must match the model exactly: the same glass size wired transposed is a
    # different panel (the Solum 2.6" and the Hanshow 2.66" are 296x152 vs 152x296), and streaming
    # rows of the wrong length garbles the image.
    candidates = [
        m
        for m in PANEL_MODELS
        if m.controller == family
        and m.matches_atc_size(config.screen_w, config.screen_h)
        and m.colors == config.screen_colors
    ]
    if len(candidates) != 1:
        raise UnsupportedTagError(
            f"no OpenDisplay panel model for ATC '{type_name}' "
            f"({config.screen_w}x{config.screen_h}, {config.screen_colors} colour plane(s), "
            f"controller {family or 'unknown'}); the Telink firmware's drivers cover the "
            "PanelIC 1000-1032 line only"
        )
    return candidates[0]


def _hex(value: int) -> str:
    return f"0x{value:x}"


def convert_to_od_config(config: DeviceConfig) -> ODConfigResult:
    """Build an OpenDisplay config for a tag from its ATC dynamic config.

    Raises:
        UnsupportedTagError: when the panel has no OpenDisplay model, or the tag reports no EPD
            pinout (without pins there is nothing to drive).
    """
    if config.epd_pinout is None:
        raise UnsupportedTagError("the tag reported no EPD pinout (epd_enabled is off)")
    panel = match_panel(config)
    epd = config.epd_pinout
    warnings: list[str] = []

    pins = {name: atc_pin_to_od(getattr(epd, name)) for name in ("reset", "dc", "busy", "cs", "clk", "mosi")}
    missing = [n for n, p in pins.items() if p == PIN_NONE]
    if missing:
        raise UnsupportedTagError(f"EPD pin(s) not assigned by the tag: {', '.join(missing)}")

    color_scheme = _color_scheme(config)
    if panel.colors == 2 and color_scheme == _COLOR_BWY and not panel.name.endswith("_BWY"):
        warnings.append(
            f"panel is yellow (BWY) but the matched model {panel.name} is documented as BWR; "
            "the second plane drives yellow on this glass, so images need BWY dithering"
        )

    if config.screen_w_offset or config.screen_h_offset:
        warnings.append(
            f"ATC applies a RAM offset (w {config.screen_w_offset}, h {config.screen_h_offset}); "
            f"OpenDisplay has no offset field -- {panel.name}'s driver applies its own, confirm on hardware"
        )

    # Panel power. SystemConfig.pwr_pin carries no polarity; the Telink firmware asserts it LOW
    # (OD_TLSR_PWR_ACTIVE_LOW, default 1), which is what every ATC board read so far uses. An
    # active-high enable would be driven backwards by that build, so it is left unset instead.
    pwr_pin = atc_pin_to_od(epd.enable)
    if pwr_pin != PIN_NONE and not epd.enable_invert:
        warnings.append(
            f"panel power enable {od_pin_name(pwr_pin)} is active-high, but the Telink firmware asserts "
            "pwr_pin LOW by default; it is left unset -- build the firmware with "
            "OD_TLSR_PWR_ACTIVE_LOW=0 and set pwr_pin by hand"
        )
        pwr_pin = PIN_NONE
    enable1 = atc_pin_to_od(epd.enable1)
    if enable1 != PIN_NONE:
        warnings.append(f"second panel enable {od_pin_name(enable1)} has no OpenDisplay field; not mapped")
    if epd.flash_cs:
        warnings.append("external flash is not mapped (no flash support in the Telink firmware yet)")
    if config.nfc_pinout is not None:
        warnings.append("NFC front end is not mapped (the Telink firmware has no NFC support)")

    try:
        battery_pin = atc_pin_to_od(config.adc_pinout)
    except ValueError:
        battery_pin = PIN_NONE
        warnings.append(f"ATC adc_pinout 0x{config.adc_pinout:04X} is not a single pin; battery not measured")
    else:
        if battery_pin == PIN_NONE:
            warnings.append("the tag reports no ADC pin; battery voltage will not be measured")

    warnings.append("SystemConfig.ic_type is 0: opendisplay-protocol has no ICType for the Telink TLSR825x yet")
    if pwr_pin != PIN_NONE:
        warnings.append(
            f"pwr_pin {od_pin_name(pwr_pin)} is active-low: correct only for the Telink firmware "
            "(which asserts pwr_pin LOW); other OpenDisplay firmwares drive it HIGH"
        )
    warnings.append(f"panel model {panel.name} was matched by controller and size, not verified on hardware")

    packets: list[dict[str, Any]] = [
        {
            "id": "1",
            "name": "system_config",
            "fields": {
                "ic_type": "0",
                "communication_modes": "0x1",  # BLE
                "device_flags": _hex(1 if pwr_pin != PIN_NONE else 0),
                "pwr_pin": f"0x{pwr_pin:02x}",
                "pwr_pin_2": "0xff",
                "pwr_pin_3": "0xff",
                "reserved": "0x0",
            },
        },
        {
            "id": "2",
            "name": "manufacturer_data",
            "fields": {
                "manufacturer_id": "0",
                "board_type": "0",
                "board_revision": "0x0",
                "simple_config_driver_index": "0",
                "simple_config_display_index": "0",
                "simple_config_power_index": "0",
                "simple_config_configured_at": "0",
                "reserved": "0x0",
            },
        },
        {
            "id": "4",
            "name": "power_option",
            "fields": {
                "power_mode": str(_POWER_MODE_BATTERY),
                # ATC's ADC pin is the one the Telink firmware drives high and measures to read
                # the supply (Telink's battery-check method); OpenDisplay carries it here.
                "battery_sense_pin": _hex(battery_pin),
            },
        },
        {
            "id": "32",
            "name": "display",
            "fields": {
                "instance_number": "0x0",
                "display_technology": str(_DISPLAY_TECH_E_PAPER),
                "panel_ic_type": str(panel.panel_ic),
                "pixel_width": _hex(panel.width),
                "pixel_height": _hex(panel.height),
                "legacy_tagtype": _hex(config.hw_type),
                "rotation": str(panel.rotation),
                "reset_pin": _hex(pins["reset"]),
                "busy_pin": _hex(pins["busy"]),
                "dc_pin": _hex(pins["dc"]),
                "cs_pin": f"0x{pins['cs']:02x}",
                "data_pin": _hex(pins["mosi"]),
                "partial_update_support": "0",
                "color_scheme": str(color_scheme),
                "transmission_modes": _hex(_TX_MODES_TELINK),
                "clk_pin": _hex(pins["clk"]),
            },
        },
    ]

    if config.led_pinout is not None:
        led = config.led_pinout
        packets.append(
            {
                "id": "33",
                "name": "led",
                "fields": {
                    "instance_number": "0x0",
                    "led_type": str(_LED_TYPE_RGB),
                    "led_1_r": _hex(atc_pin_to_od(led.r)),
                    "led_2_g": _hex(atc_pin_to_od(led.g)),
                    "led_3_b": _hex(atc_pin_to_od(led.b)),
                    "led_4": "0xff",
                    "led_flags": _hex(0x7 if led.inverted else 0),
                },
            }
        )

    return ODConfigResult(
        config_json={
            "version": 1,
            "minor_version": 1,
            "packets": packets,
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "exported_by": "py-atc-ble-oepl",
        },
        panel=panel,
        warnings=warnings,
    )
