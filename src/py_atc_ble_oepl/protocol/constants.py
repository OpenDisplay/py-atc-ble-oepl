"""ATC BLE protocol constants."""

# ATC Device Identifiers
MANUFACTURER_ID = 0x1337  # 4919 decimal
SERVICE_UUID = "00001337-0000-1000-8000-00805f9b34fb"

# Protocol Commands
CMD_GET_DISPLAY_INFO = bytes([0x00, 0x05])   # Query device display capabilities
CMD_GET_DYNAMIC_CONFIG = bytes([0x00, 0x11]) # Read full device settings

# Protocol Response Prefixes
DYNAMIC_CONFIG_RESPONSE_PREFIX = bytes([0x00, 0xCD])  # Response to CMD_GET_DYNAMIC_CONFIG

# Protocol Parameters
BLE_MIN_RESPONSE_LENGTH = 33  # Minimum valid response length for CMD_GET_DISPLAY_INFO
DYNAMIC_CONFIG_MIN_LENGTH = 45  # 2-byte prefix + 43-byte base payload
