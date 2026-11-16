# Chapter 4: Input

**Tag:** [`chapter-04`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-04) · [Index](README.md) · Previous: [Chapter 3](03-sim-session.md) · Next: [Chapter 5](05-control-and-output.md)

**What it teaches:** one interface for every device, and how to fake analog pedals and steering
with digital keys.

## Read in this order

1. [`src/carla_rig/input/base.py`](../src/carla_rig/input/base.py): `update(dt)` uses **sim** time;
   `on_vehicle_status` is the feedback hook (blinker resync now, force feedback later).
2. The pure functions at the top of
   [`src/carla_rig/input/keyboard_mouse.py`](../src/carla_rig/input/keyboard_mouse.py): `ramp`,
   `approach`, `keyboard_steer`, `mouse_steer`, `next_blinker`. No pygame, so they are unit-tested.
3. `KeyboardMouseInput.update` in the same file: why this class is the **only** reader of the pygame
   event queue.
4. The stubs [`input/wheel.py`](../src/carla_rig/input/wheel.py) and
   [`input/serial_stalk.py`](../src/carla_rig/input/serial_stalk.py): read the docstrings as a
   preview of chapter 8 (calibration, steering lock, serial protocol, background thread).

## Grep

```bash
grep -n "# TUNE:" src/carla_rig/input/keyboard_mouse.py
```

```bash
grep -rn "SWAP\[hardware\]" src/carla_rig/input/
```

## Try it

Change `input.keyboard.throttle_rise_rate` in the config to `0.5` and feel how gentle the throttle
becomes. Then press M and steer with the mouse; set `input.mouse.centering_rate: 0` to remove the spring.
