"""ATC BLE operation exceptions."""


class ATCError(Exception):
    """Base exception for ATC BLE operations."""


class BLEConnectionError(ATCError):
    """BLE connection to device failed."""


class BLEProtocolError(ATCError):
    """BLE protocol communication error."""


class BLETimeoutError(ATCError):
    """BLE operation timed out."""


class ProtocolError(ATCError):
    """General protocol error (alias for BLEProtocolError for API compatibility)."""
