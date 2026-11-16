# Chapter 3: The CARLA session

**Tag:** [`chapter-03`](https://github.com/dwikis17/carla-rig-poc/tree/chapter-03) · [Index](README.md) · Previous: [Chapter 2](02-contracts-and-config.md) · Next: [Chapter 4](04-input.md)

**What it teaches:** why synchronous mode, and why cleanup must always run.

## Read in this order

1. The module docstring of [`src/carla_rig/sim/session.py`](../src/carla_rig/sim/session.py): a
   client that crashes while the world is in sync mode leaves the server frozen, waiting for a tick
   that never comes.
2. `__enter__` and `__exit__`: why setup failures are cleaned up inside `__enter__` (Python never
   calls `__exit__` if `__enter__` raises).
3. `_configure_world`: sync mode, fixed time step, substepping, and why the Traffic Manager must be
   put in sync mode too.
4. `_spawn_ego`, `_spawn_sensors`, `_spawn_camera`: one `queue.Queue` per sensor; `sensor_tick = 0`
   so the camera produces one image per tick.
5. `close`: the cleanup order (stop sensors → destroy actors in one batch → TM out of sync → restore
   settings), and why every step is isolated so one failure can't skip the rest.
6. [`src/carla_rig/utils/frames.py`](../src/carla_rig/utils/frames.py): `wait_for_frame` drops stale
   images and fails loudly on a skipped frame; event sensors are drained without waiting.

## Grep

```bash
grep -n "# WHY:" src/carla_rig/sim/session.py src/carla_rig/utils/frames.py
```

```bash
grep -n "# TUNE:" src/carla_rig/sim/session.py
```

## Try it

With a server running, start the client and press Ctrl+C. The log ends with
`CARLA session cleaned up`, and a second client starts without hanging.
