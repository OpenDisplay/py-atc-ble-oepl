"""ATC BLE protocol constants."""

# ATC Device Identifiers
MANUFACTURER_ID = 0x1337  # 4919 decimal
SERVICE_UUID = "00001337-0000-1000-8000-00805f9b34fb"

# Protocol Commands
CMD_GET_DISPLAY_INFO = bytes([0x00, 0x05])  # Query device display capabilities
CMD_INIT = bytes([0x01, 0x01])  # Initialize connection before use

# Protocol Parameters
INIT_DELAY_SECONDS = 2.0  # Delay after CMD_INIT before device is ready
BLE_MIN_RESPONSE_LENGTH = 33  # Minimum valid response length for CMD_GET_DISPLAY_INFO
