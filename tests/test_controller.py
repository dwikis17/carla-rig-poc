"""Controller: blinker auto-cancel, light-state mapping, VehicleControl mapping (fake carla)."""

import carla  # this is tests/fake_carla.py, installed by conftest.py
import pytest

from carla_rig.config import ControlConfig
from carla_rig.control.vehicle import (
    BlinkerAutoCancel,
    VehicleController,
    build_vehicle_control,
    compute_light_bits,
)
from carla_rig.state import InputState

LS = carla.VehicleLightState


def test_fake_carla_in_use():
    assert getattr(carla, "IS_FAKE", False), "tests must never import the real carla module"


# --- BlinkerAutoCancel -----------------------------------------------------------------------

def make_cancel():
    return BlinkerAutoCancel(arm_threshold=0.35, center_threshold=0.08)


def test_blinker_cancels_after_turn_and_return():
    b = make_cancel()
    assert b.update("left", 0.0) == "left"
    assert b.update("left", -0.2) == "left"   # not past arm yet
    assert b.update("left", -0.5) == "left"   # armed
    assert b.update("left", -0.2) == "left"   # returning, not centred yet
    assert b.update("left", -0.05) == "off"   # centred → cancel


def test_blinker_stays_off_even_if_input_keeps_saying_left():
    b = make_cancel()
    b.update("left", 0.0)
    b.update("left", -0.6)
    assert b.update("left", 0.0) == "off"
    for _ in range(5):
        assert b.update("left", 0.0) == "off"  # stale input value must not re-enable it


def test_blinker_no_cancel_without_arming():
    b = make_cancel()
    b.update("right", 0.0)
    for steer in (0.1, 0.2, 0.0, -0.05):
        assert b.update("right", steer) == "right"


def test_blinker_arming_is_direction_matched():
    b = make_cancel()
    b.update("left", 0.0)
    b.update("left", 0.6)                      # steering RIGHT while left blinker on
    assert b.update("left", 0.0) == "left"     # must not cancel


def test_new_request_after_cancel_is_adopted():
    b = make_cancel()
    b.update("left", 0.0)
    b.update("left", -0.6)
    b.update("left", 0.0)                      # cancelled
    b.update("off", 0.0)                       # input resyncs (keyboard on_vehicle_status)
    assert b.update("left", 0.0) == "left"     # driver presses Q again


def test_switching_sides_disarms():
    b = make_cancel()
    b.update("left", 0.0)
    b.update("left", -0.6)                     # armed for left
    assert b.update("right", -0.6) == "right"  # switch side mid-turn
    assert b.update("right", 0.0) == "right"   # must NOT cancel: right never armed


# --- light-state mapping ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "blinker, expected",
    [("left", LS.LeftBlinker), ("right", LS.RightBlinker), ("off", LS.NONE)],
)
def test_blinker_maps_to_light_state(blinker, expected):
    assert compute_light_bits(0, blinker, braking=False, reverse=False) == int(expected)


def test_other_lights_are_preserved():
    start = int(LS.LowBeam | LS.Position | LS.LeftBlinker)
    bits = compute_light_bits(start, "right", braking=False, reverse=False)
    assert bits == int(LS.LowBeam | LS.Position | LS.RightBlinker)


def test_brake_and_reverse_lamps():
    bits = compute_light_bits(0, "off", braking=True, reverse=True)
    assert bits == int(LS.Brake | LS.Reverse)


# --- VehicleControl mapping + controller -------------------------------------------------------

def test_build_vehicle_control():
    c = build_vehicle_control(InputState(throttle=0.4, brake=0.1, steer=-0.3, hand_brake=True, reverse=True))
    assert (c.throttle, c.brake, c.steer, c.hand_brake, c.reverse) == (0.4, 0.1, -0.3, True, True)
    assert c.manual_gear_shift is False


class FakeVehicle:
    def __init__(self, lights=LS.NONE):
        self.lights = lights
        self.controls = []
        self.light_calls = []

    def apply_control(self, control):
        self.controls.append(control)

    def get_light_state(self):
        return self.lights

    def set_light_state(self, state):
        self.lights = state
        self.light_calls.append(state)


def test_controller_clamps_and_applies():
    ctl = VehicleController(ControlConfig())
    v = FakeVehicle()
    applied = ctl.apply(v, InputState(throttle=1.5, brake=-0.2, steer=-3.0))
    assert (applied.throttle, applied.brake, applied.steer) == (1.0, 0.0, -1.0)
    assert v.controls[-1].throttle == 1.0 and v.controls[-1].steer == -1.0


def test_controller_sets_lights_only_on_change_and_keeps_headlights():
    ctl = VehicleController(ControlConfig())
    v = FakeVehicle(lights=LS.LowBeam)
    ctl.apply(v, InputState(blinker="left"))
    ctl.apply(v, InputState(blinker="left"))
    assert len(v.light_calls) == 1
    assert int(v.lights) == int(LS.LowBeam | LS.LeftBlinker)


def test_controller_auto_cancel_end_to_end():
    ctl = VehicleController(ControlConfig(blinker_cancel_arm_threshold=0.35, blinker_cancel_center_threshold=0.08))
    v = FakeVehicle()
    for steer in (0.0, 0.5, 0.2):
        assert ctl.apply(v, InputState(blinker="right", steer=steer)).blinker == "right"
    assert ctl.apply(v, InputState(blinker="right", steer=0.0)).blinker == "off"
    assert int(v.lights) & int(LS.RightBlinker) == 0
