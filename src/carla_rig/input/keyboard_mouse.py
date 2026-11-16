"""Keyboard + mouse ``InputSource`` — the PoC driver input.

Role in the architecture
------------------------
Turns pygame key/mouse events into an ``InputState``. A keyboard is DIGITAL (a key is down or up),
but a car needs ANALOG throttle/brake/steer, so we simulate analog with time-based ramps.

Structure
---------
* Pure functions at the top (``ramp``, ``approach``, ``keyboard_steer``, ``mouse_steer``,
  ``next_blinker``): all the math, no pygame, unit-tested in tests/test_keyboard_ramp.py.
* ``KeyboardMouseInput`` at the bottom: thin pygame glue that reads events and calls the math.

Import rules
------------
May import ``pygame`` (lazily, inside the class), ``state``, ``config``, ``input.base``.
Must NOT import ``carla``.

Controls
--------
W throttle · S brake · A/D steer · Q/E left/right blinker · Space handbrake (hold) ·
R reverse toggle · C chase/driver camera · M mouse steering · H help · Esc quit

# SWAP[hardware]: this whole file is replaced by input/wheel.py (steering + pedals) merged with
# input/serial_stalk.py (turn signal, horn, buttons). Select it with `input.source` in the config.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from carla_rig.config import InputConfig
from carla_rig.input.base import InputSource
from carla_rig.state import Blinker, InputState, VehicleStatus

if TYPE_CHECKING:  # pragma: no cover
    import pygame  # noqa: F401


# =============================================================================
# Pure math (no pygame) — unit-testable
# =============================================================================


def clamp(value: float, lo: float, hi: float) -> float:
    return lo if value < lo else hi if value > hi else value


def ramp(value: float, pressed: bool, rise_rate: float, fall_rate: float, dt: float) -> float:
    """Simulate an analog pedal from a digital key.

    While ``pressed`` the value rises by ``rise_rate`` per second, otherwise it decays by
    ``fall_rate`` per second; always clamped to [0, 1].

    # WHY: slamming throttle 0 → 1 in one 50 ms tick makes the car lurch and spins wheels;
    # a ramp lets you feather the pedal by tapping the key.
    # TUNE: input.keyboard.throttle_rise_rate / throttle_fall_rate / brake_rise_rate / brake_fall_rate
    """
    if pressed:
        value += rise_rate * dt
    else:
        value -= fall_rate * dt
    return clamp(value, 0.0, 1.0)


def approach(current: float, target: float, rate: float, dt: float) -> float:
    """Move ``current`` toward ``target`` by at most ``rate * dt`` without overshooting."""
    step = rate * dt
    if current < target:
        return min(current + step, target)
    if current > target:
        return max(current - step, target)
    return current


def keyboard_steer(
    current: float, left: bool, right: bool, steer_rate: float, return_rate: float, dt: float
) -> float:
    """Ease steering toward full lock while A/D is held, and auto-center when released.

    Both keys held (or neither) → target 0 (auto-center).
    # TUNE: input.keyboard.steer_rate (how fast you reach lock), steer_return_rate (self-centering).
    """
    if left and not right:
        target, rate = -1.0, steer_rate
    elif right and not left:
        target, rate = 1.0, steer_rate
    else:
        target, rate = 0.0, return_rate
    return clamp(approach(current, target, rate, dt), -1.0, 1.0)


def mouse_steer(current: float, dx_pixels: float, sensitivity: float, centering_rate: float, dt: float) -> float:
    """Accumulate horizontal mouse motion into steer, with an optional centering spring.

    ``steer += dx * sensitivity`` then the spring pulls toward 0 at ``centering_rate`` units/s,
    clamped to [-1, 1]. The spring is applied after the movement so a moving mouse always wins.
    # TUNE: input.mouse.sensitivity (steer per pixel), input.mouse.centering_rate (0 = off)
    """
    value = clamp(current + dx_pixels * sensitivity, -1.0, 1.0)
    if centering_rate > 0:
        value = approach(value, 0.0, centering_rate, dt)
    return value


def next_blinker(current: Blinker, pressed: Blinker) -> Blinker:
    """Toggle logic for the Q (left) / E (right) keys.

    * same side pressed again → off
    * other side pressed      → switch to that side
    * off                     → pressed side
    """
    if pressed == "off":
        return current
    return "off" if current == pressed else pressed


# =============================================================================
# pygame glue
# =============================================================================


class KeyboardMouseInput(InputSource):
    """Reads pygame events once per tick and turns them into an InputState.

    Requires that the pygame display is already initialised (HUD does that) — pygame only
    delivers keyboard events to a window.

    # WHY: (this class also pumps window events (QUIT, Esc, H)) pygame has ONE event queue. If the HUD
    # also called pygame.event.get(), events would be randomly split between the two readers.
    """

    def __init__(self, cfg: InputConfig) -> None:
        import pygame  # lazy: keeps the pure functions importable without pygame installed

        self._pg = pygame
        self._kb = cfg.keyboard
        self._mouse = cfg.mouse

        self._throttle = 0.0
        self._brake = 0.0
        self._steer = 0.0
        self._blinker: Blinker = "off"
        self._reverse = False
        self._mouse_mode = False
        self._closed = False

        if cfg.mouse.start_enabled:  # TUNE: input.mouse.start_enabled
            self._set_mouse_mode(True)

    # ------------------------------------------------------------------ helpers

    def _set_mouse_mode(self, enabled: bool) -> None:
        pg = self._pg
        self._mouse_mode = enabled
        # Grab = the OS cursor can't leave the window, so you can keep moving one way for full lock.
        pg.event.set_grab(enabled)
        pg.mouse.set_visible(not enabled)
        pg.mouse.get_rel()  # discard motion accumulated before the switch (avoids a steering jump)

    # ------------------------------------------------------------------ InputSource API

    def update(self, dt: float) -> InputState:
        pg = self._pg
        quit_requested = False
        toggle_camera = False
        toggle_help = False
        mouse_dx = 0.0

        # 1) Discrete events (one-shot actions and toggles).
        for event in pg.event.get():
            if event.type == pg.QUIT:  # window close button
                quit_requested = True
            elif event.type == pg.KEYDOWN:
                key = event.key
                if key == pg.K_ESCAPE:
                    quit_requested = True
                elif key == pg.K_q:
                    self._blinker = next_blinker(self._blinker, "left")
                elif key == pg.K_e:
                    self._blinker = next_blinker(self._blinker, "right")
                elif key == pg.K_r:
                    self._reverse = not self._reverse
                elif key == pg.K_c:
                    toggle_camera = True
                elif key == pg.K_h:
                    toggle_help = True
                elif key == pg.K_m:
                    self._set_mouse_mode(not self._mouse_mode)
            elif event.type == pg.MOUSEMOTION and self._mouse_mode:
                mouse_dx += event.rel[0]

        # 2) Continuous state (held keys) → simulated analog.
        # SWAP[hardware]: real pedals and a wheel are already analog — WheelInput (input/wheel.py)
        # reads joystick axes directly and needs no ramps; only dead zones and calibration.
        keys = pg.key.get_pressed()
        kb = self._kb
        self._throttle = ramp(self._throttle, keys[pg.K_w], kb.throttle_rise_rate, kb.throttle_fall_rate, dt)
        self._brake = ramp(self._brake, keys[pg.K_s], kb.brake_rise_rate, kb.brake_fall_rate, dt)

        if self._mouse_mode:
            self._steer = mouse_steer(self._steer, mouse_dx, self._mouse.sensitivity, self._mouse.centering_rate, dt)
        else:
            self._steer = keyboard_steer(
                self._steer, keys[pg.K_a], keys[pg.K_d], kb.steer_rate, kb.steer_return_rate, dt
            )

        return InputState(
            throttle=self._throttle,
            brake=self._brake,
            steer=self._steer,
            blinker=self._blinker,
            hand_brake=bool(keys[pg.K_SPACE]),
            reverse=self._reverse,
            quit=quit_requested,
            toggle_camera=toggle_camera,
            toggle_help=toggle_help,
            mouse_steering=self._mouse_mode,
        )

    def on_vehicle_status(self, status: VehicleStatus) -> None:
        # Mirror the controller's auto-cancel so the next Q press turns the blinker ON again
        # instead of "off" (which is what the stale toggle state would do).
        self._blinker = status.blinker

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            # Always give the cursor back, even if we crash: a grabbed, hidden cursor is maddening.
            self._pg.event.set_grab(False)
            self._pg.mouse.set_visible(True)
        except Exception:  # noqa: BLE001 — display may already be gone
            pass
