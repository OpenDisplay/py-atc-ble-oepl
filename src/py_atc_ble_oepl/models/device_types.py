"""ATC/OEPL device type name map and color scheme mapping, sourced from atc_ble_oepl_uploader.html."""

# Maps screen_type ID → color_scheme value (0=MONO, 1=BWR, 2=BWY, 3=BWRY).
# Used to refine the color_scheme reported by the 0005 response, which only
# gives a color count (1/2/3) and cannot distinguish BWR from BWY.
SCREEN_TYPE_COLOR_SCHEME: dict[int, int] = {
    1: 2,
    2: 2,
    3: 2,
    4: 0,
    5: 2,
    6: 2,  # BWY, BWY, BWY, MONO, BWY, BWY
    7: 1,
    8: 1,
    9: 1,
    10: 0,
    11: 1,
    12: 1,  # BWR×3, MONO, BWR×2
    13: 0,
    14: 1,
    15: 1,
    16: 1,
    17: 3,
    18: 1,  # MONO, BWR×3, BWRY, BWR
    19: 1,
    20: 1,
    21: 1,
    22: 1,
    23: 1,
    24: 1,  # BWR×6
    25: 0,
    26: 0,
    27: 1,
    28: 1,
    29: 0,
    30: 0,  # MONO×2, BWR×2, MONO×2
    31: 2,
    32: 0,
    33: 1,
    34: 1,
    35: 2,  # BWY, MONO, BWR×2, BWY
    36: 3,
    37: 3,
    38: 3,
    39: 3,
    40: 3,
    41: 3,  # BWRY×6
    42: 2,
    43: 1,
    44: 1,
    45: 1,
    46: 1,
    47: 1,  # BWY, BWR×5
}

DEVICE_TYPES: dict[int, str] = {
    65535: "Dynamic (HW Config Tab)",
    1: "350 HS BWY UC",
    2: "350 HS BWY UC Inverted",
    3: "350 HS BWY SSD",
    4: "350 HS BW UC",
    5: "200 HS BWY SSD",
    6: "750 HS BWY UC",
    7: "350 HS BWR UC",
    8: "350 HS BWR SSD",
    9: "266 HS BWR SSD",
    10: "213 HS BW UC",
    11: "213 Gici BWR SSD",
    12: "290 Gici BWR SSD",
    13: "213 Gici BW ST",
    14: "970 TI BWR",
    15: "1200 TI BWR",
    16: "213 HS BWR SSD",
    17: "350 HS BWRY JD",
    18: "154 HS BWR H SSD",
    19: "213 HS BWR UC",
    20: "420 HS BWR SSD",
    21: "420 HS BWR UC",
    22: "420 Gici BWR SSD",
    23: "1200 TI BWR V2",
    24: "290 HS BWR SSD",
    25: "213 HS BW SSD",
    26: "581 TI BW",
    27: "581 TI BWR",
    28: "213 Gici BWR UC",
    29: "213 Gici BW SSD",
    30: "213 Gici BW UC",
    31: "583 HS BWY UC",
    32: "350 HS BW SSD",
    33: "266 HS BWR SSD Offset",
    34: "581 TI BWR UC",
    35: "346 HS BWY UC",
    36: "290 WO BWRY JD",
    37: "750 HS BWRY JD",
    38: "200 HS BWRY JD",
    39: "290 WO BWRY JD V2",
    40: "260 HS BWRY JD",
    41: "260 WO BWRY JD V2",
    42: "420 HS BWY SSD",
    43: "290 HS BWR SSD V2",
    44: "583 HS BWR UC",
    45: "213 HS BWR SSD V2",
    46: "290 HS BWR SSD V3",
    47: "213 HS BWR UC V2",
}


def get_device_type_name(screen_type: int) -> str:
    """Return human-readable name for an ATC screen_type value.

    Args:
        screen_type: Screen type identifier from the 00CD dynamic config response

    Returns:
        Name string, or 'unknown (0xXXXX)' for unrecognised types
    """
    if screen_type in DEVICE_TYPES:
        return DEVICE_TYPES[screen_type]
    return f"unknown (0x{screen_type:04X})"


# The maker codes in the type names above. The others in them are panel
# controllers (UC, SSD, ST, UC_PRO, JD), which say nothing about the maker.
_MANUFACTURER_CODES: dict[str, str] = {
    "HS": "Hanshow",
    "Gici": "Gicisky",
    # TI is the panel controller on atc1441's page, but the tags with it are
    # SoluM's large M3s: an M3 12.2" runs as 15, "1200 TI BWR" (atc_ble_oepl
    # channel on the OpenEPaperLink Discord).
    "TI": "SoluM",
}


def guess_manufacturer(screen_type: int) -> str | None:
    """Guess who made a tag from its ATC screen type.

    Read from the maker code in the type's name ("350 HS BWY UC" is a
    Hanshow). Returns ``None`` for types whose maker is not known, such as
    the "WO" ones, and for the dynamic type.

    Args:
        screen_type: Screen type identifier from the 00CD dynamic config response
    """
    name = DEVICE_TYPES.get(screen_type, "")
    return next((_MANUFACTURER_CODES[code] for code in name.split() if code in _MANUFACTURER_CODES), None)
