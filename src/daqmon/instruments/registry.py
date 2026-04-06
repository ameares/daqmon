"""Instrument registry and factory.

To add a new instrument:

1. Create a driver class in a new module under ``daqmon/instruments/``.
2. Call :func:`register` in ``daqmon/instruments/__init__.py``.

That's it – the rest of the program discovers the instrument automatically.
"""

from __future__ import annotations

import logging
from typing import Callable

from .base import InstrumentBase

logger = logging.getLogger(__name__)

# Maps instrument_type string -> constructor callable.
# The callable must accept keyword arguments: port, baudrate, timeout.
_REGISTRY: dict[str, Callable[..., InstrumentBase]] = {}


def register(name: str, factory: Callable[..., InstrumentBase]) -> None:
    """Register an instrument factory under the given type name.

    ``name`` should match the ``instrument_type`` string used in scan config
    JSON files (compared case-insensitively).
    """
    _REGISTRY[name.lower()] = factory
    logger.debug("Registered instrument: %s -> %s", name, factory)


def make_instrument(
    instrument_type: str,
    port: str = "/dev/ttyUSB0",
    baudrate: int = 9600,
    timeout: float = 10.0,
) -> InstrumentBase:
    """Instantiate the instrument registered under *instrument_type*.

    Args:
        instrument_type: Key used when the instrument was registered, e.g.
            ``"hp34970a"``, ``"fluke45"``, ``"random"``.
        port: Serial port path (ignored by non-serial instruments).
        baudrate: Baud rate (ignored by non-serial instruments).
        timeout: Serial read timeout in seconds (ignored by non-serial instruments).

    Raises:
        ValueError: If *instrument_type* has not been registered.
    """
    key = instrument_type.lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        known = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown instrument_type {instrument_type!r}. "
            f"Registered instruments: {known}"
        )
    return factory(port=port, baudrate=baudrate, timeout=timeout)


def registered_types() -> list[str]:
    """Return the sorted list of registered instrument type names."""
    return sorted(_REGISTRY)
