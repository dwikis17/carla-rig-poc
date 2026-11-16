"""Layer contracts: the ONLY data that crosses layer boundaries.

Role in the architecture
------------------------
Every layer speaks in terms of these two dataclasses:

* ``InputState``    — produced by ``input/`` (any InputSource), consumed by ``control/``,
                      ``output/hud.py`` and ``output/logger.py``. Describes what the DRIVER is doing.
* ``VehicleStatus`` — produced by ``main.py`` from the simulator after each tick, consumed by
                      ``output/``. Describes what the VEHICLE / WORLD actually did.

Import rules
------------
This module must stay dependency-free (stdlib only). It must NOT import ``carla`` or ``pygame``:
the input layer imports it, and the input layer is not allowed to know CARLA exists.

# WHY: keeping the contract in plain dataclasses means you can unit-test, record, replay or
# network-stream driver input without a simulator or a window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

# The three legal blinker values. A Literal keeps typos ("Left", "none") visible to type-checkers.
Blinker = Literal["left", "right", "off"]
BLINKER_VALUES: tuple[str, ...] = ("left", "right", "off")


@dataclass
class InputState:
    """What the driver is commanding THIS tick, normalised and hardware-agnostic.

    Ranges are fixed by contract so any InputSource (keyboard, wheel, network, replay file) can
    feed the same controller:

    * ``throttle``  ∈ [0, 1]
    * ``brake``     ∈ [0, 1]
    * ``steer``     ∈ [-1, 1]   (-1 = full left, +1 = full right, matching carla.VehicleControl)
    """

    throttle: float = 0.0
    brake: float = 0.0
    steer: float = 0.0
    blinker: Blinker = "off"
    hand_brake: bool = False
    reverse: bool = False
    quit: bool = False
    # One-shot: True for exactly ONE update() after the key press, then False again.
    # WHY: if it stayed True while held, the camera would flip every tick.
    toggle_camera: bool = False
    # One-shot toggle for the help overlay (H). Kept here so the HUD never reads pygame events itself.
    toggle_help: bool = False
    # Informational only (HUD shows it): True while mouse steering is active.
    mouse_steering: bool = False

    def clamped(self) -> "InputState":
        """Return a copy with analog values forced into their contract ranges.

        # WHY: the controller calls this defensively so a buggy InputSource (or an uncalibrated
        # pedal reporting 1.03) can never push out-of-range values into CARLA.
        """
        return InputState(
            throttle=min(max(self.throttle, 0.0), 1.0),
            brake=min(max(self.brake, 0.0), 1.0),
            steer=min(max(self.steer, -1.0), 1.0),
            blinker=self.blinker if self.blinker in BLINKER_VALUES else "off",
            hand_brake=self.hand_brake,
            reverse=self.reverse,
            quit=self.quit,
            toggle_camera=self.toggle_camera,
            toggle_help=self.toggle_help,
            mouse_steering=self.mouse_steering,
        )


@dataclass
class VehicleStatus:
    """Snapshot of the ego vehicle after one simulation tick.

    ``throttle``/``brake``/``steer``/``blinker`` are the values the CONTROLLER actually applied
    (after clamping and blinker auto-cancel), which may differ from the raw InputState.
    """

    frame: int
    sim_time: float          # seconds since the episode started (snapshot.timestamp.elapsed_seconds)
    speed_kmh: float
    x: float                 # world position in metres (CARLA uses a left-handed, Z-up frame)
    y: float
    z: float
    yaw: float               # degrees
    throttle: float
    brake: float
    steer: float
    blinker: Blinker
    hand_brake: bool
    reverse: bool
    collided_this_tick: bool = False
    collision_with: Optional[str] = None   # type_id of the other actor, e.g. "vehicle.tesla.model3"
    lane_invasion: bool = False
    # RESEARCH: add experiment fields here (and in output/logger.py's column list), e.g.
    #   time_headway_s, distance_to_lead_m, lead_vehicle_id, trial_condition, scenario_event.
    # Compute them in main.py step 5 where you have access to the world snapshot.
