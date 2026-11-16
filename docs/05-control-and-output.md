# Chapter 5: Control and output

**Tag:** [`chapter-05`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-05) · [Index](README.md) · Previous: [Chapter 4](04-input.md) · Next: [Chapter 6](06-main-loop.md)

**What it teaches:** turning driver intent into CARLA commands (including a software turn-signal
stalk), drawing instruments from sim time, and logging every tick without stalling the loop.

## Read in this order

1. `BlinkerAutoCancel` in [`src/carla_rig/control/vehicle.py`](../src/carla_rig/control/vehicle.py):
   arm when steering past a threshold in the blinker's direction, cancel when back near centre.
   Note why it only reacts to *changes* in the input.
2. `compute_light_bits` and `VehicleController.apply` (same file): change only the blinker, brake
   and reverse bits so headlights survive; send `set_light_state` only when the bits change.
3. [`src/carla_rig/output/hud.py`](../src/carla_rig/output/hud.py): `bgra_to_rgb` (numpy, no
   per-pixel loop), the arc speedometer, and why the blinker flashes on **sim** time.
4. [`src/carla_rig/output/logger.py`](../src/carla_rig/output/logger.py): buffered rows, flush every
   N, a copy of the resolved config next to each log.

## Grep

```bash
grep -n "# WHY:" src/carla_rig/control/vehicle.py src/carla_rig/output/*.py
```

```bash
grep -rn "SWAP\[" src/carla_rig/output/
```

## Try it

Drive, signal left with Q, turn left past the threshold and straighten up: the blinker cancels.
Then open the newest `runs/*/log.csv` and find the row where `blinker` goes from `left` to `off`.
