"""Pure input math: ramps, steering easing, mouse clamp/spring, blinker toggle. No pygame needed."""

import subprocess
import sys
from pathlib import Path

import pytest

from carla_rig.input.keyboard_mouse import (
    approach,
    keyboard_steer,
    mouse_steer,
    next_blinker,
    ramp,
)

DT = 0.05


# --- ramp ---------------------------------------------------------------------------------

def test_ramp_rises_while_pressed():
    assert ramp(0.0, True, rise_rate=2.0, fall_rate=4.0, dt=DT) == pytest.approx(0.1)


def test_ramp_reaches_full_in_expected_time():
    v = 0.0
    for _ in range(10):  # 10 × 0.05 s = 0.5 s at 2.0/s → 1.0
        v = ramp(v, True, 2.0, 4.0, DT)
    assert v == pytest.approx(1.0)


def test_ramp_clamps_at_one():
    assert ramp(0.99, True, 2.0, 4.0, DT) == 1.0


def test_ramp_decays_when_released_and_clamps_at_zero():
    assert ramp(0.5, False, 2.0, 4.0, DT) == pytest.approx(0.3)
    assert ramp(0.1, False, 2.0, 4.0, DT) == 0.0


# --- approach / keyboard steering -------------------------------------------------------------

def test_approach_does_not_overshoot():
    assert approach(0.95, 1.0, rate=10.0, dt=DT) == 1.0
    assert approach(-0.02, 0.0, rate=10.0, dt=DT) == 0.0
    assert approach(0.3, 0.3, rate=10.0, dt=DT) == 0.3


def test_steer_left_eases_toward_minus_one():
    s = keyboard_steer(0.0, left=True, right=False, steer_rate=2.0, return_rate=3.0, dt=DT)
    assert s == pytest.approx(-0.1)
    for _ in range(100):
        s = keyboard_steer(s, True, False, 2.0, 3.0, DT)
    assert s == -1.0


def test_steer_auto_centers_when_released():
    s = keyboard_steer(0.5, left=False, right=False, steer_rate=2.0, return_rate=3.0, dt=DT)
    assert s == pytest.approx(0.35)
    for _ in range(100):
        s = keyboard_steer(s, False, False, 2.0, 3.0, DT)
    assert s == 0.0


def test_both_steer_keys_cancel_out():
    assert keyboard_steer(0.2, True, True, 2.0, 3.0, DT) == pytest.approx(0.05)


# --- mouse steering --------------------------------------------------------------------------

def test_mouse_accumulates_motion():
    assert mouse_steer(0.0, dx_pixels=100, sensitivity=0.003, centering_rate=0.0, dt=DT) == pytest.approx(0.3)


@pytest.mark.parametrize("dx, expected", [(10_000, 1.0), (-10_000, -1.0)])
def test_mouse_clamps(dx, expected):
    assert mouse_steer(0.0, dx, 0.003, 0.0, DT) == expected


def test_mouse_spring_pulls_to_center():
    assert mouse_steer(0.5, 0, 0.003, centering_rate=1.0, dt=DT) == pytest.approx(0.45)
    assert mouse_steer(-0.01, 0, 0.003, centering_rate=1.0, dt=DT) == 0.0


def test_mouse_zero_spring_holds_position():
    assert mouse_steer(0.5, 0, 0.003, centering_rate=0.0, dt=DT) == 0.5


# --- blinker toggle --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "current, pressed, expected",
    [
        ("off", "left", "left"),
        ("left", "left", "off"),      # same side again → off
        ("left", "right", "right"),   # opposite side → switch
        ("off", "right", "right"),
        ("right", "right", "off"),
        ("right", "left", "left"),
    ],
)
def test_next_blinker(current, pressed, expected):
    assert next_blinker(current, pressed) == expected


# --- architecture rule ---------------------------------------------------------------------

def test_input_layer_does_not_import_carla():
    """Rule 1: the input layer must not import carla. Checked in a clean interpreter."""
    src = Path(__file__).resolve().parents[1] / "src"
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import carla_rig.input.base, carla_rig.input.keyboard_mouse,"
        " carla_rig.input.wheel, carla_rig.input.serial_stalk;"
        "assert 'carla' not in sys.modules, 'input layer imported carla'" % str(src)
    )
    subprocess.run([sys.executable, "-c", code], check=True)
