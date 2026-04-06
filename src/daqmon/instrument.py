"""Backward-compatibility shim.  Import from ``daqmon.instruments`` instead."""

from .instruments.hp34970a import (  # noqa: F401
    FUNC_MAP,
    RANGE_MAP,
    TC_TYPE_MAP,
    HP34970A,
    _RJUN_SCPI_TO_KEY,
    normalize_range,
)
