"""ATC/OEPL device type name map, sourced from atc_ble_oepl_uploader.html."""

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


def get_device_type_name(hw_type: int) -> str:
    """Return human-readable name for an OEPL hw_type value.

    Args:
        hw_type: Hardware type identifier from device advertising/config

    Returns:
        Name string, or 'unknown (0xXXXX)' for unrecognised types
    """
    if hw_type in DEVICE_TYPES:
        return DEVICE_TYPES[hw_type]
    return f"unknown (0x{hw_type:04X})"
