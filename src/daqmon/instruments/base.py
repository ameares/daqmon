"""Abstract base class for all instrument drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..config import ScanConfig


class InstrumentBase(ABC):
    """Common interface that every instrument driver must implement.

    The scan loop in scanner.py interacts exclusively through this interface,
    making it instrument-agnostic.  Two timing models are supported:

    Hardware-timed (e.g. HP34970A)
        The instrument has its own internal scan timer.  ``fetch_sweep``
        returns ``None`` until the instrument's buffer holds a complete sweep,
        then removes and returns that sweep.

    Software-timed (e.g. Fluke45, RandomInstrument)
        The driver tracks elapsed time internally.  ``fetch_sweep`` returns
        ``None`` until ``scan_interval`` seconds have passed, then acquires
        a measurement synchronously and returns it.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the connection to the instrument (serial port, socket, etc.)."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection to the instrument."""

    @abstractmethod
    def idn(self) -> str:
        """Return an identification string for the instrument."""

    @abstractmethod
    def configure(self, scan_cfg: "ScanConfig") -> None:
        """Apply the full scan configuration to the instrument.

        Called once before :meth:`start`.  Implementations should store any
        config state they need for subsequent :meth:`fetch_sweep` calls.
        """

    @abstractmethod
    def start(self) -> None:
        """Arm the instrument and begin scanning.

        For hardware-timed instruments this typically sends an INIT command.
        For software-timed instruments it records the start timestamp.
        """

    @abstractmethod
    def stop(self) -> None:
        """Stop scanning and release any instrument resources.

        Called in the ``finally`` block of the scan loop, so implementations
        must be safe to call even if :meth:`start` was never called.
        """

    @abstractmethod
    def fetch_sweep(self) -> list[tuple[float, int]] | None:
        """Return one complete sweep or ``None`` if data are not yet available.

        A *sweep* is a list of ``(value, channel_number)`` pairs — one entry
        per configured channel.  The scan loop calls this repeatedly (with
        ``poll_interval`` sleeps between calls) until a sweep is returned.

        Returning ``None`` tells the scan loop to sleep and try again.
        """
