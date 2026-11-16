"""Abstract ``InputSource``: the single seam between driver hardware and the rest of the program.

Role in the architecture
------------------------
Everything that can drive the car — keyboard, USB wheel, Arduino stalk, a replay file, a network
socket — implements this interface and returns an ``InputState`` each tick. ``main.py`` picks the
implementation from ``input.source`` in the config and never touches the concrete class again.

Import rules
------------
May import ``state`` and ``config``. Must NOT import ``carla`` (enforced by convention + a test):
input code has to be testable and reusable without a simulator.

# SWAP[hardware]: real hardware means writing ONE new subclass of InputSource
# (see input/wheel.py and input/serial_stalk.py) and adding it to ``make_input_source`` in main.py.
# Nothing in control/, sim/ or output/ changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from carla_rig.state import InputState, VehicleStatus


class InputSource(ABC):
    """Produces one ``InputState`` per simulation tick."""

    @abstractmethod
    def update(self, dt: float) -> InputState:
        """Read the device(s) and return the driver's command for this tick.

        ``dt`` is the SIMULATED time step (world.fixed_delta_seconds), not wall time.
        # WHY sim time: ramps and springs then behave identically whether the loop runs in real
        # time, slower (overruns) or faster (realtime_pacing: false).

        Must never block for long: it runs inside the tick budget.
        """

    def on_vehicle_status(self, status: VehicleStatus) -> None:
        """Optional feedback after each tick (default: ignore).

        Used by the keyboard source to resync its blinker toggle when the controller auto-cancels
        it, the way a real stalk physically clicks back to centre.
        # SWAP[hardware]: a force-feedback wheel would use this to set centering force from
        # status.speed_kmh; a physical speedometer driver could also live behind this hook.
        """

    def close(self) -> None:
        """Release devices (ungrab mouse, close serial port, stop threads). Must be idempotent."""

    # Convenience so sources can be used with `with`.
    def __enter__(self) -> "InputSource":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False
