"""ATC BLE operation exceptions."""


class ATCError(Exception):
    """Base exception for ATC BLE operations."""


class BLEConnectionError(ATCError):
    """BLE connection to device failed."""


class BLEProtocolError(ATCError):
    """BLE protocol communication error."""


class BLETimeoutError(ATCError):
    """BLE operation timed out."""


class ProtocolError(BLEProtocolError):
    """General protocol error.

    Subclasses :class:`BLEProtocolError` so that ``except BLEProtocolError``
    catches it, as its name and documentation have always implied. It was
    previously a sibling, which silently escaped such handlers.
    """
