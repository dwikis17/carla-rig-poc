# Chapter 2: Contracts and config

**Tag:** [`chapter-02`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-02) · [Index](README.md) · Previous: [Chapter 1](01-scaffold.md) · Next: [Chapter 3](03-sim-session.md)

**What it teaches:** layers talk **only** through two dataclasses, and every tunable lives in one
YAML file that is checked at startup instead of failing halfway through a session.

## Read in this order

1. [`src/carla_rig/state.py`](../src/carla_rig/state.py): `InputState` (what the driver commands)
   and `VehicleStatus` (what the car did). Note the fixed ranges and why `toggle_camera` is one-shot.
   `clamped()` is the safety net for out-of-range hardware.
2. [`config/default.yaml`](../config/default.yaml): every value, grouped, with inline comments.
   Look for the camera FOV formula and its worked example.
3. [`src/carla_rig/config.py`](../src/carla_rig/config.py): `_build` / `_coerce` reject unknown keys
   and wrong types (including the `bool`-is-an-`int` trap). `validate` checks combinations, such as
   the substep rule `fixed_delta_seconds <= max_substep_delta_time * max_substeps`.

## Grep

```bash
grep -n "# WHY:" src/carla_rig/state.py src/carla_rig/config.py
```

```bash
grep -n "RESEARCH:" src/carla_rig/state.py
```

## Try it

Break the config on purpose (set `fixed_delta_seconds: 0.2`) and load it:

```bash
PYTHONPATH=src python -c "from carla_rig.config import load_config; load_config('config/default.yaml')"
```
