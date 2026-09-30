"""ATC dynamic config -> OpenDisplay config, against configs read from real tags."""

import json
from pathlib import Path

import pytest

from py_atc_ble_oepl.models.device_config import DeviceConfig, EPDPinout, FlashPinout, LEDPinout, NFCPinout
from py_atc_ble_oepl.od_config import (
    PANEL_MODELS,
    PIN_NONE,
    UnsupportedTagError,
    atc_pin_to_od,
    convert_to_od_config,
    match_panel,
    od_pin_name,
)

FIXTURES = json.loads((Path(__file__).parent / "fixtures" / "atc_dynamic_configs.json").read_text())["configs"]


def _config(raw: dict) -> DeviceConfig:
    parts = {
        "epd_pinout": EPDPinout,
        "led_pinout": LEDPinout,
        "nfc_pinout": NFCPinout,
        "flash_pinout": FlashPinout,
    }
    kwargs = {k: (parts[k](**v) if k in parts and v is not None else v) for k, v in raw.items()}
    return DeviceConfig(**kwargs)


def _tag(screen_type: int) -> DeviceConfig:
    return _config(next(c for c in FIXTURES if c["screen_type"] == screen_type))


def _display(result) -> dict:
    return next(p for p in result.config_json["packets"] if p["id"] == "32")["fields"]


class TestPins:
    @pytest.mark.parametrize(
        ("atc", "od"),
        [(0x0001, 0), (0x0080, 7), (0x0110, 12), (0x0380, 31), (0x0401, 32), (0, PIN_NONE)],
    )
    def test_atc_word_to_od_number(self, atc, od):
        assert atc_pin_to_od(atc) == od

    @pytest.mark.parametrize("bad", [0x0103, 0x0500 | 0x01, 0x0100])
    def test_rejects_words_that_are_not_one_pin(self, bad):
        with pytest.raises(ValueError):
            atc_pin_to_od(bad)

    def test_names(self):
        assert od_pin_name(12) == "PB4"
        assert od_pin_name(PIN_NONE) == "-"


class TestSupportedTag:
    """ATC type 9, '266 HS BWR SSD': the Hanshow 2.66" BWR panel, 152 sources x 296 gates."""

    def test_matches_the_hanshow_266_in_native_orientation(self):
        result = convert_to_od_config(_tag(9))
        assert result.panel.name == "SSD16XX_HS_266_BWR"
        d = _display(result)
        assert d["panel_ic_type"] == "1031"
        assert (int(d["pixel_width"], 16), int(d["pixel_height"], 16)) == (152, 296)
        assert d["color_scheme"] == "1"

    def test_transposed_size_is_a_different_panel(self):
        # The Solum 2.6" (SSD1619_026, 296x152) is not this 152x296 glass: matching it garbled
        # the image on a real tag. Only the transposed ATC size selects it.
        cfg = _tag(9)
        cfg.screen_w, cfg.screen_h = 296, 152
        assert match_panel(cfg).name == "SSD1619_026_BWR"

    def test_pins_come_from_the_tag(self):
        d = _display(convert_to_od_config(_tag(9)))
        got = {k: int(d[k], 16) for k in ("reset_pin", "dc_pin", "busy_pin", "cs_pin", "clk_pin", "data_pin")}
        # PD4, PD7, PA1, PB4, PB5, PB6
        assert got == {"reset_pin": 28, "dc_pin": 31, "busy_pin": 1, "cs_pin": 12, "clk_pin": 13, "data_pin": 14}

    def test_active_low_panel_power_is_mapped_for_the_telink_convention(self):
        result = convert_to_od_config(_tag(9))
        system = next(p for p in result.config_json["packets"] if p["id"] == "1")["fields"]
        assert system["pwr_pin"] == "0x15"  # PC5 = 2 * 8 + 5 = 21
        assert system["device_flags"] == "0x1"  # OD_DEVICE_FLAG_PWR_PIN
        assert any("active-low" in w and "PC5" in w for w in result.warnings)

    def test_active_high_panel_power_is_left_unset(self):
        cfg = _tag(9)
        assert cfg.epd_pinout is not None
        cfg.epd_pinout.enable_invert = False
        result = convert_to_od_config(cfg)
        system = next(p for p in result.config_json["packets"] if p["id"] == "1")["fields"]
        assert system["pwr_pin"] == "0xff"
        assert system["device_flags"] == "0x0"
        assert any("OD_TLSR_PWR_ACTIVE_LOW=0" in w for w in result.warnings)

    def test_battery_pin_from_adc_pinout(self):
        power = next(p for p in convert_to_od_config(_tag(9)).config_json["packets"] if p["id"] == "4")["fields"]
        assert power["battery_sense_pin"] == "0xb"  # ATC 0x0108 = PB3 = 1 * 8 + 3

    def test_led_mapped(self):
        led = next(p for p in convert_to_od_config(_tag(9)).config_json["packets"] if p["id"] == "33")["fields"]
        assert (int(led["led_1_r"], 16), int(led["led_2_g"], 16), int(led["led_3_b"], 16)) == (26, 27, 7)
        assert led["led_flags"] == "0x7"  # ATC not inverted = active-low = all three OD invert bits

    def test_reports_what_it_cannot_carry(self):
        text = " ".join(convert_to_od_config(_tag(9)).warnings)
        assert "offset" in text  # ATC's 8-pixel offset: the model's driver has its own
        assert "NFC" in text
        assert "ic_type" in text
        assert "not verified on hardware" in text


class TestHanshowBwy:
    def test_type_5_maps_to_1032_as_bwy(self):
        # ATC reports 152x200; the glass is wired 200 sources x 152 gates (verified on the tag).
        result = convert_to_od_config(_tag(5))
        d = next(p for p in result.config_json["packets"] if p["id"] == "32")["fields"]
        assert (d["panel_ic_type"], d["pixel_width"], d["pixel_height"], d["color_scheme"]) == (
            "1032",
            "0xc8",
            "0x98",
            "2",
        )
        assert not any("documented as BWR" in w for w in result.warnings)

    @pytest.mark.parametrize(("screen_type", "rotation"), [(5, "3"), (9, "1")])
    def test_natural_face_is_upright(self, screen_type, rotation):
        # The BWY tag is held portrait, the 2.66" landscape; both glasses are wired the other way.
        assert _display(convert_to_od_config(_tag(screen_type)))["rotation"] == rotation


class TestUnsupportedTags:
    @pytest.mark.parametrize(
        ("screen_type", "why"),
        [
            (10, "UC"),  # 2.13" UC 128x250: the 128x250 model is SSD, not UC
        ],
    )
    def test_refused_rather_than_guessed(self, screen_type, why):
        with pytest.raises(UnsupportedTagError, match=why):
            convert_to_od_config(_tag(screen_type))

    def test_no_epd_pinout(self):
        cfg = _tag(9)
        cfg.epd_pinout = None
        with pytest.raises(UnsupportedTagError, match="no EPD pinout"):
            convert_to_od_config(cfg)

    def test_colour_count_must_match(self):
        cfg = _tag(9)
        cfg.screen_colors = 1  # there is no BW model of this glass
        with pytest.raises(UnsupportedTagError):
            match_panel(cfg)


def test_model_table_is_the_legacy_line_plus_1031_to_1034():
    assert [m.panel_ic for m in PANEL_MODELS] == list(range(1000, 1035))


def test_output_parses_as_a_py_opendisplay_config():
    """The JSON must be what `opendisplay write-config` accepts, byte-serialisable included."""
    config_json = pytest.importorskip("opendisplay.models.config_json")
    serializer = pytest.importorskip("opendisplay.protocol.config_serializer")

    cfg = config_json.config_from_json(convert_to_od_config(_tag(9)).config_json)
    d = cfg.displays[0]
    assert (d.panel_ic_type, d.pixel_width, d.pixel_height, d.color_scheme) == (1031, 152, 296, 1)
    assert (d.reset_pin, d.dc_pin, d.busy_pin, d.cs_pin, d.clk_pin, d.data_pin) == (28, 31, 1, 12, 13, 14)
    assert cfg.system.pwr_pin == 21
    assert cfg.power.battery_sense_pin == 11
    assert len(serializer.serialize_display_config(d)) > 0


def test_nebular_350_bwy_model():
    # Verified on the tag: held landscape, upright at rotation 1; colours, mirroring and edges correct.
    m = next(m for m in PANEL_MODELS if m.panel_ic == 1033)
    assert (m.controller, m.width, m.height, m.colors, m.rotation) == ("UC", 184, 384, 2, 1)


class TestTi970:
    def test_type_14_maps_to_1034_with_both_halves(self):
        result = convert_to_od_config(_tag(14))
        d = _display(result)
        assert (d["panel_ic_type"], d["pixel_width"], d["pixel_height"], d["color_scheme"]) == (
            "1034",
            "0x3c0",
            "0x2a0",
            "1",
        )
        assert int(d["cs_pin"], 16) == 12 and int(d["reserved_pin_2"], 16) == 17  # PB4, PC1
        sysc = next(p for p in result.config_json["packets"] if p["id"] == "1")["fields"]
        assert int(sysc["pwr_pin"], 16) == 27 and int(sysc["pwr_pin_2"], 16) == 18  # PD3, PC2
        power = next(p for p in result.config_json["packets"] if p["id"] == "4")["fields"]
        assert power["battery_sense_pin"] == "0x8"  # PB0
        assert d["rotation"] == "2"  # verified on the board: upright at 180

    def test_single_controller_panels_leave_the_second_pins_alone(self):
        result = convert_to_od_config(_tag(9))
        assert "reserved_pin_2" not in _display(result)
        sysc = next(p for p in result.config_json["packets"] if p["id"] == "1")["fields"]
        assert sysc["pwr_pin_2"] == "0xff"
