# Chapter 6: The main loop

**Tag:** [`chapter-06`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-06) · [Index](README.md) · Previous: [Chapter 5](05-control-and-output.md) · Next: [Chapter 7](07-testing.md)

**What it teaches:** the 8 steps of one tick and why they run in that order, matching the camera
image to its frame, and keeping simulated time in step with the wall clock.

## Read in this order

1. `run_loop` in [`src/carla_rig/main.py`](../src/carla_rig/main.py), top to bottom. Each step is
   numbered: input → control → tick → camera frame → status → HUD + flip → log → pace.
2. Step 2: why control is applied **before** `tick()` (no one-frame input lag).
3. Step 5: why speed and pose come from the world snapshot, not `vehicle.get_velocity()`.
4. Step 8: what an overrun is, and why the deadline resets after a long stall instead of catching up.
5. `run` and `main`: the order things are opened and closed, and the SIGTERM handler.
6. `make_input_source`: the one line that changes for real hardware.

## Grep

```bash
grep -n "# WHY:\|SWAP\[\|RESEARCH:" src/carla_rig/main.py
```

## Try it

Set `world.npc_vehicles: 80` and `camera.width/height` to 1920×1080, drive for a minute, and quit.
Compare the run summary (real-time factor, overruns, worst loop time) with the default settings.
