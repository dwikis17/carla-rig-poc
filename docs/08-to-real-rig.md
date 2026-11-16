# Chapter 8: From PoC to real rig

**Tag:** [`chapter-08`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-08) · [Index](README.md) · Previous: [Chapter 7](07-testing.md)

**What it teaches:** how to follow the `SWAP[...]` tags to replace the keyboard with a wheel and a
stalk, and the single screen with several, without touching the rest of the loop.

## Read in this order

1. The "From PoC to real rig" checklist in the [project README](../README.md#from-poc-to-real-rig).
2. Every hardware extension point:

   ```bash
   grep -rn "SWAP\[hardware\]" src/
   ```

   Start with the docstring of [`input/wheel.py`](../src/carla_rig/input/wheel.py) (axis mapping,
   pedal inversion, dead zones, steering lock), then
   [`input/serial_stalk.py`](../src/carla_rig/input/serial_stalk.py) (`TURN:L` protocol, background
   reader thread, physical speedometer).
3. Every multi-monitor extension point:

   ```bash
   grep -rn "SWAP\[multi-monitor\]" src/
   ```

   In order: cameras in `sim/session.py → _spawn_camera` (same eye point, yaw step = FOV + bezel
   angle), the spanning borderless window in `output/hud.py`, one flip per frame in `main.py`.
4. Where experiments plug in:

   ```bash
   grep -rn "RESEARCH:" src/
   ```

5. The Troubleshooting section of the [project README](../README.md#troubleshooting).

## Try it

Implement `WheelInput.update()` for your wheel, set `input.source: wheel`, and run the same tests:
nothing outside `input/` should need to change.
