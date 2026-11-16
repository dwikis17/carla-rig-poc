"""Vehicle controller: ``InputState`` → ``carla.VehicleControl`` + vehicle light state.

Role in the architecture
------------------------
The ONLY place where driver intent becomes CARLA commands. It also holds the small amount of
"car behaviour" that belongs to the vehicle rather than the input device:

* blinker auto-cancel (a real stalk clicks off after you complete the turn),
* turn-signal / brake / reverse lamps via ``carla.VehicleLightState``.

Because the controller only sees ``InputState``, it works identically for keyboard, wheel or replay.

Import rules
------------
May import ``carla``, ``state``, ``config``. Must NOT import ``pygame`` or ``input/``.
The pure blinker logic (``BlinkerAutoCancel``) doesn't touch carla, so it is tested directly;
the carla-facing parts are tested with a fake ``carla`` module (tests/test_controller.py).
"""

from __future__ import annotations

from typing import Any, Optional

import carla

from carla_rig.config import ControlConfig
from carla_rig.state import Blinker, InputState


class BlinkerAutoCancel:
    """Software model of a turn-signal stalk's self-cancelling cam.

    Rules
    -----
    1. A NEW request from the input (value differs from the previous input value) is adopted.
    2. While a blinker is on, steering past ``arm`` IN THE BLINKER'S DIRECTION arms the cancel
       (left blinker → steer < -arm; right → steer > +arm), like the cam engaging as you turn.
    3. Once armed, |steer| returning below ``center`` turns the blinker off.

    # WHY edge-detect the input (rule 1): an input source may keep reporting "left" after we
    # auto-cancelled (e.g. it has no feedback hook). Re-adopting it every tick would turn the blinker
    # straight back on. Only a CHANGE in the input counts as the driver touching the stalk.
    # WHY direction-matched arming: a lane-change wiggle to the right shouldn't cancel a left signal.
    # TUNE: control.blinker_cancel_arm_threshold / control.blinker_cancel_center_threshold
    """

    def __init__(self, arm_threshold: float, center_threshold: float) -> None:
        self.arm = arm_threshold
        self.center = center_threshold
        self.state: Blinker = "off"
        self._armed = False
        self._last_input: Blinker = "off"

    def update(self, requested: Blinker, steer: float) -> Blinker:
        if requested != self._last_input:
            self._last_input = requested
            self.state = requested
            self._armed = False

        if self.state == "off":
            self._armed = False
            return self.state

        direction = -1.0 if self.state == "left" else 1.0
        if steer * direction > self.arm:
            self._armed = True
        elif self._armed and abs(steer) < self.center:
            self.state = "off"
            self._armed = False
        # RESEARCH: log the auto-cancel moment here if you study signalling behaviour.
        return self.state


def build_vehicle_control(state: InputState) -> "carla.VehicleControl":
    """Map a (clamped) InputState onto a carla.VehicleControl."""
    ctrl = carla.VehicleControl()
    ctrl.throttle = float(state.throttle)
    ctrl.brake = float(state.brake)
    ctrl.steer = float(state.steer)
    ctrl.hand_brake = bool(state.hand_brake)
    # WHY reverse as a flag (not gear=-1): with manual_gear_shift=False CARLA's automatic gearbox
    # handles forward gears, and `reverse=True` makes throttle push the car backwards.
    ctrl.reverse = bool(state.reverse)
    ctrl.manual_gear_shift = False
    return ctrl


def compute_light_bits(current_bits: int, blinker: Blinker, braking: bool, reverse: bool) -> int:
    """Return new light-state bits: update blinker/brake/reverse lamps, keep every other lamp.

    # WHY bit-twiddle instead of assigning: headlights, fog lights etc. may be set by the server,
    # a scenario, or a future headlight switch. Overwriting the whole mask would turn them off.
    """
    LS = carla.VehicleLightState
    managed = int(LS.LeftBlinker) | int(LS.RightBlinker) | int(LS.Brake) | int(LS.Reverse)
    bits = int(current_bits) & ~managed
    if blinker == "left":
        bits |= int(LS.LeftBlinker)
    elif blinker == "right":
        bits |= int(LS.RightBlinker)
    if braking:
        bits |= int(LS.Brake)
    if reverse:
        bits |= int(LS.Reverse)
    return bits


class VehicleController:
    """Applies InputState to the ego vehicle each tick."""

    def __init__(self, cfg: ControlConfig) -> None:
        self._blinker = BlinkerAutoCancel(cfg.blinker_cancel_arm_threshold, cfg.blinker_cancel_center_threshold)
        self._light_bits: Optional[int] = None  # last mask we sent; None = not read from vehicle yet

    def apply(self, vehicle: Any, state: InputState) -> InputState:
        """Send controls + lights to ``vehicle``; return the InputState as actually applied.

        The returned state has clamped analog values and the post-auto-cancel blinker. ``main.py``
        uses it to build ``VehicleStatus`` and feeds it back to the input source.
        """
        applied = state.clamped()
        applied.blinker = self._blinker.update(applied.blinker, applied.steer)

        # SWAP[hardware]: nothing here changes for real hardware — that's the point of the contract.
        # (Only if a stalk cancels mechanically, disable auto-cancel via the config thresholds.)
        vehicle.apply_control(build_vehicle_control(applied))

        if self._light_bits is None:
            # Read once so we preserve whatever lamps the vehicle already has on.
            self._light_bits = int(vehicle.get_light_state())
        new_bits = compute_light_bits(self._light_bits, applied.blinker, applied.brake > 0.0, applied.reverse)
        if new_bits != self._light_bits:
            # WHY only on change: set_light_state is an RPC; sending it every tick wastes budget.
            # The lamp FLASHING is done by CARLA's renderer, we only switch the blinker on/off.
            vehicle.set_light_state(carla.VehicleLightState(new_bits))
            self._light_bits = new_bits
        return applied
