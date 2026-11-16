"""STUB: USB steering wheel + pedals via ``pygame.joystick``.

Role in the architecture
------------------------
Drop-in replacement for ``KeyboardMouseInput``. Selected with ``input.source: wheel``.
Only this file (plus, optionally, ``serial_stalk.py``) needs to exist for real hardware.

Import rules
------------
May import ``pygame``, ``state``, ``config``, ``input.base``, ``input.serial_stalk``.
Must NOT import ``carla``.

# SWAP[hardware]: implement this class to replace the keyboard. Everything below is a guide.

Implementation guide
--------------------
Library
    ``pygame.joystick`` (already a dependency). Logitech G29/G920, Thrustmaster T300, Fanatec etc.
    all enumerate as standard HID game controllers. Call ``pygame.joystick.init()`` and open
    ``pygame.joystick.Joystick(cfg.device_index)``. Print ``joy.get_name()``, ``get_numaxes()``,
    ``get_numbuttons()`` once at startup — it saves hours.

Finding the axis/button mapping
    Mappings differ per model AND per OS driver. Write a 20-line script that prints every
    ``joy.get_axis(i)`` while you turn the wheel / press each pedal, then put the indices in
    ``input.wheel.steer_axis / throttle_axis / brake_axis`` (config, not code). Buttons (paddles,
    D-pad) map the same way: ``joy.get_button(i)`` → e.g. paddle-right = reverse toggle.

Calibration
    * Pedal inversion: many pedal sets report +1 when released and -1 when fully pressed.
      Normalise to [0, 1] with ``p = (1 - raw) / 2`` when ``invert_pedals`` is true,
      else ``p = (raw + 1) / 2``.
    * Dead zones: ``p = 0 if p < pedal_deadzone else (p - dz) / (1 - dz)`` — re-scaling keeps the
      full 0..1 range after removing noise near rest. Same idea for steering around centre with
      ``steer_deadzone``.
    * Steering lock: a real wheel rotates e.g. ±450° (``wheel_range_deg: 900``), and pygame reports
      that as axis -1..+1. CARLA's ``steer = ±1`` means "the vehicle's max road-wheel angle"
      (~70° on most blueprints). Convert via degrees so the ratio is explicit and tunable:
          wheel_deg = axis * wheel_range_deg / 2
          steer     = clamp(wheel_deg / max_steer_angle_deg, -1, 1)
      With max_steer_angle_deg = wheel_range_deg / 2 the full physical rotation maps to full lock
      (1:1). A smaller max_steer_angle_deg = quicker steering ratio. TUNE: input.wheel.*
    * Ask the participant to centre the wheel at startup and store an axis offset if your driver
      doesn't self-calibrate.

Event pumping
    pygame only updates joystick values when the event queue is pumped. This class must call
    ``pygame.event.get()`` every tick (and handle QUIT / Esc / C / H exactly like the keyboard
    source does), because it REPLACES the keyboard source as the only event reader.

Merging with the turn-signal stalk
    Hold a ``SerialStalkInput`` (input/serial_stalk.py) as a member, and in ``update()``:
        state = InputState(throttle=..., brake=..., steer=...)      # from the wheel
        stalk = self._stalk.update(dt)                               # never blocks (thread-backed)
        state.blinker = stalk.blinker
        state.hand_brake = stalk.hand_brake or wheel_handbrake_button
        return state
    That way main.py still sees exactly ONE InputSource. ``close()`` must close both.

Force feedback (later)
    pygame has no FFB API. Use the vendor SDK (Logitech G HUB SDK) or ``evdev`` on Linux, and drive
    it from ``on_vehicle_status()`` using ``status.speed_kmh`` for speed-dependent centring force.
"""

from __future__ import annotations

from carla_rig.config import InputConfig
from carla_rig.input.base import InputSource
from carla_rig.state import InputState


class WheelInput(InputSource):
    """USB wheel + pedals. NOT IMPLEMENTED — see the module docstring for the full recipe."""

    def __init__(self, cfg: InputConfig) -> None:
        # SWAP[hardware]: open the joystick here:
        #   import pygame; pygame.joystick.init()
        #   self._joy = pygame.joystick.Joystick(cfg.wheel.device_index)
        # and optionally the stalk:  self._stalk = SerialStalkInput(cfg)
        self._cfg = cfg.wheel

    def update(self, dt: float) -> InputState:
        # SWAP[hardware]: 1) pygame.event.get() (QUIT/Esc/C/H), 2) read axes, 3) invert + dead-zone
        # pedals, 4) degrees-based steering conversion, 5) merge the serial stalk, 6) return InputState.
        raise NotImplementedError(
            "WheelInput is a stub. Implement it (see src/carla_rig/input/wheel.py docstring) "
            "or set input.source: keyboard_mouse in your config."
        )

    def close(self) -> None:
        # SWAP[hardware]: self._joy.quit(); self._stalk.close()
        pass
