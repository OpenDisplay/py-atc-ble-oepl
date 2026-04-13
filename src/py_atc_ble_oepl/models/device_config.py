"""Device configuration data model, parsed from the 0011 dynamic config response."""

from dataclasses import dataclass


@dataclass
class EPDPinout:
    """EPD display GPIO pin assignments (26 bytes, present only when EPD enabled)."""

    reset: int
    dc: int
    busy: int
    busy_s: int
    cs: int
    cs_s: int
    clk: int
    mosi: int
    enable: int
    enable1: int
    enable_invert: bool
    flash_cs: int
    pin_config_sleep: int
    pin_enable: int
    pin_enable_sleep: int


@dataclass
class LEDPinout:
    """LED GPIO pin assignments (7 bytes, present only when LED enabled)."""

    r: int
    g: int
    b: int
    inverted: bool


@dataclass
class NFCPinout:
    """NFC GPIO pin assignments (8 bytes, present only when NFC enabled)."""

    sda: int
    scl: int
    cs: int
    irq: int


@dataclass
class FlashPinout:
    """Flash GPIO pin assignments (8 bytes, present only when flash enabled)."""

    cs: int
    clk: int
    miso: int
    mosi: int


@dataclass
class DeviceConfig:
    """Full device configuration from the 0011 dynamic config response (00CD).

    Base payload is always 43 bytes. Optional pinout sections follow only
    if the corresponding *_enabled flag is set.

    Attributes:
        screen_type: EPD panel type identifier
        hw_type: OEPL hardware type (maps to DEVICE_TYPES)
        screen_functions: Feature flags bitmask
        wh_inverted_ble: W/H inversion flag used by BLE protocol
        wh_inverted: W/H inversion flag used by device config
        screen_h: Configured screen height
        screen_w: Configured screen width
        screen_h_offset: Screen height offset
        screen_w_offset: Screen width offset
        screen_colors: Number of color planes (1=BW, 2=BWR/BWY, 3=BWRY)
        black_invert: Invert black plane
        second_color_invert: Invert second color plane
        epd_enabled: EPD pinout section present
        led_enabled: LED pinout section present
        nfc_enabled: NFC pinout section present
        flash_enabled: Flash pinout section present
        adc_pinout: ADC pin assignment
        uart_pinout: UART pin assignment
        epd_pinout: EPD GPIO assignments (None if epd_enabled is False)
        led_pinout: LED GPIO assignments (None if led_enabled is False)
        nfc_pinout: NFC GPIO assignments (None if nfc_enabled is False)
        flash_pinout: Flash GPIO assignments (None if flash_enabled is False)
    """

    screen_type: int
    hw_type: int
    screen_functions: int
    wh_inverted_ble: bool
    wh_inverted: bool
    screen_h: int
    screen_w: int
    screen_h_offset: int
    screen_w_offset: int
    screen_colors: int
    black_invert: bool
    second_color_invert: bool
    epd_enabled: bool
    led_enabled: bool
    nfc_enabled: bool
    flash_enabled: bool
    adc_pinout: int
    uart_pinout: int
    epd_pinout: EPDPinout | None = None
    led_pinout: LEDPinout | None = None
    nfc_pinout: NFCPinout | None = None
    flash_pinout: FlashPinout | None = None
