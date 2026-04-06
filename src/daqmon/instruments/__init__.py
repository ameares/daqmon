"""Instrument drivers package.

All instruments are registered here so the rest of the program only needs to
call :func:`make_instrument` with a type string from the scan config.
"""

from .base import InstrumentBase
from .fluke45 import Fluke45
from .hp34970a import HP34970A
from .random_instrument import RandomInstrument
from .registry import make_instrument, register, registered_types

# Register all built-in drivers.
# Default baud rates are set here; the CLI overrides them from config.json
# when an explicit baudrate is present.
register("hp34970a", HP34970A)
register("fluke45", Fluke45)
register("random", lambda port, baudrate, timeout: RandomInstrument())

__all__ = [
    "InstrumentBase",
    "HP34970A",
    "Fluke45",
    "RandomInstrument",
    "make_instrument",
    "register",
    "registered_types",
]
