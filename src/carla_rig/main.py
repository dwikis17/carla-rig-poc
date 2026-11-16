"""Entry point: wire the layers together and run the fixed-step simulation loop.

Role in the architecture
------------------------
The composition root. It is the only module that knows about EVERY layer; the layers themselves
only know ``state.py`` and ``config.py``. Read ``run_loop`` top to bottom to understand one tick.

Usage::

    python -m carla_rig.main --config config/default.yaml

Import rules
------------
May import everything in the package. Nothing else may import ``main``.

Cleanup guarantee
-----------------
Esc / window close → InputState.quit → loop breaks → ``with SimSession`` exits.
Ctrl+C (SIGINT) and SIGTERM → KeyboardInterrupt → same ``with`` / ``finally`` blocks run.
Any exception → same. So the server is always taken out of sync mode and all actors are destroyed.
"""

from __future__ import annotations

import argparse
import logging
import math
import signal
import sys
import time
from dataclasses import dataclass

from carla_rig.config import Config, ConfigError, InputConfig, load_config
from carla_rig.input.base import InputSource
from carla_rig.state import InputState, VehicleStatus
from carla_rig.utils.frames import FrameTimeoutError, drain, wait_for_frame

log = logging.getLogger("carla_rig")


def make_input_source(cfg: InputConfig) -> InputSource:
    """Pick the InputSource implementation named by ``input.source``.

    # SWAP[hardware]: this is the ONLY line of main.py that changes for real hardware — set
    # `input.source: wheel` (WheelInput in input/wheel.py, which merges SerialStalkInput from
    # input/serial_stalk.py) once those stubs are implemented.
    Imports are local so a missing optional dependency (e.g. pyserial) only matters if selected.
    """
    if cfg.source == "keyboard_mouse":
        from carla_rig.input.keyboard_mouse import KeyboardMouseInput
        return KeyboardMouseInput(cfg)
    if cfg.source == "wheel":
        from carla_rig.input.wheel import WheelInput
        return WheelInput(cfg)
    if cfg.source == "serial":
        from carla_rig.input.serial_stalk import SerialStalkInput
        return SerialStalkInput(cfg)
    raise ConfigError(f"unknown input.source {cfg.source!r}")  # config.validate() should catch this first


@dataclass
class LoopStats:
    """Timing bookkeeping for the end-of-run summary."""

    ticks: int = 0
    overruns: int = 0
    worst_loop_s: float = 0.0
    total_loop_s: float = 0.0
    sim_time: float = 0.0
    wall_start: float = 0.0
    last_overrun_wall: float = -math.inf

    def summary(self, dt: float) -> str:
        wall = time.perf_counter() - self.wall_start if self.wall_start else 0.0
        avg_ms = 1000 * self.total_loop_s / self.ticks if self.ticks else 0.0
        pct = 100 * self.overruns / self.ticks if self.ticks else 0.0
        rtf = self.sim_time / wall if wall > 0 else 0.0
        return (
            f"ticks={self.ticks}  sim={self.sim_time:.1f}s  wall={wall:.1f}s  real-time factor={rtf:.2f}\n"
            f"loop avg={avg_ms:.1f}ms  worst={1000 * self.worst_loop_s:.1f}ms  budget={1000 * dt:.1f}ms\n"
            f"overruns={self.overruns} ({pct:.1f}% of ticks)"
        )


def run_loop(cfg: Config, sim, inp: InputSource, controller, hud, logger, stats: LoopStats) -> None:
    """The fixed-step loop. The ORDER of steps matters — see the comments."""
    import pygame

    dt = cfg.world.fixed_delta_seconds  # TUNE: world.fixed_delta_seconds
    stats.wall_start = time.perf_counter()
    next_deadline = stats.wall_start
    camera_gen_seen = sim.camera_generation

    while True:
        loop_start = time.perf_counter()

        # --- 1) INPUT: read the driver ------------------------------------------------------
        # Uses SIM dt so ramps behave the same regardless of wall-clock jitter.
        state: InputState = inp.update(dt)
        if state.quit:
            log.info("quit requested")
            break
        if state.toggle_camera:
            # SWAP[multi-monitor]: with a camera rig per monitor, toggling would respawn the whole
            # set (or be disabled in driver view, which is the only view a cockpit needs).
            sim.toggle_camera()

        # --- 2) CONTROL: send commands for the step we are about to simulate -------------------
        # WHY: (before tick) in sync mode the control is consumed by the NEXT tick, so applying it
        # first means this tick's physics uses this tick's input (no one-frame input lag).
        applied = controller.apply(sim.vehicle, state)

        # --- 3) TICK: advance the world exactly one fixed step ---------------------------------
        # WHY: (we tick (sync mode)) the server waits for us, so sim time advances by exactly dt per
        # loop iteration and every sensor produces exactly one measurement for this frame id.
        frame = sim.world.tick()
        snapshot = sim.world.get_snapshot()

        # --- 4) SENSORS: fetch the camera image belonging to THIS frame -------------------------
        try:
            image = wait_for_frame(sim.camera_queue, frame, cfg.server.sensor_timeout_s)
        except FrameTimeoutError:
            if sim.camera_generation != camera_gen_seen:
                # A freshly respawned camera often misses its first frame; HUD keeps the last image.
                image = None
            else:
                raise
        camera_gen_seen = sim.camera_generation

        # --- 5) STATUS: what actually happened this tick ---------------------------------------
        # WHY: (the snapshot (not vehicle.get_velocity())) it is one consistent picture of frame N,
        # already on the client — no extra RPCs, no mixing values from different frames.
        actor = snapshot.find(sim.vehicle.id)
        tf = actor.get_transform()
        vel = actor.get_velocity()
        speed_kmh = 3.6 * math.sqrt(vel.x ** 2 + vel.y ** 2 + vel.z ** 2)  # m/s → km/h
        collisions = drain(sim.collision_queue)
        lane_events = drain(sim.lane_queue)
        status = VehicleStatus(
            frame=frame,
            sim_time=snapshot.timestamp.elapsed_seconds,
            speed_kmh=speed_kmh,
            x=tf.location.x, y=tf.location.y, z=tf.location.z,
            yaw=tf.rotation.yaw,
            throttle=applied.throttle, brake=applied.brake, steer=applied.steer,
            blinker=applied.blinker, hand_brake=applied.hand_brake, reverse=applied.reverse,
            collided_this_tick=bool(collisions),
            collision_with=collisions[-1].other_actor.type_id if collisions else None,
            lane_invasion=bool(lane_events),
        )
        # RESEARCH: compute experiment measures here from `snapshot` (e.g. find the lead vehicle in
        # the ego lane → distance_to_lead_m, time_headway_s = distance / ego speed) and add them to
        # VehicleStatus + logger columns. Scripted events (ScenarioRunner triggers, a pedestrian
        # stepping out at t=30s, trial start/stop markers) also belong at this point in the loop.
        inp.on_vehicle_status(status)  # lets the input mirror blinker auto-cancel (or drive FFB)

        # --- 6) OUTPUT: draw and present ---------------------------------------------------------
        overrun_recent = (time.perf_counter() - stats.last_overrun_wall) < cfg.hud.overrun_display_s
        hud.render(image, applied, status, sim.camera_view, overrun_recent)
        # WHY: (one flip per frame) everything (camera(s) + HUD) is composed off-screen first, then
        # shown at once.
        # SWAP[multi-monitor]: still exactly ONE flip, for the single window spanning all screens.
        pygame.display.flip()

        # --- 7) LOG: buffered, so normally just a list append -----------------------------------
        logger.write(status, applied)

        # --- 8) PACE: keep 1 sim second ≈ 1 wall second -----------------------------------------
        loop_time = time.perf_counter() - loop_start
        stats.ticks += 1
        stats.sim_time = status.sim_time
        stats.total_loop_s += loop_time
        stats.worst_loop_s = max(stats.worst_loop_s, loop_time)

        if cfg.world.realtime_pacing:  # TUNE: world.realtime_pacing
            next_deadline += dt
            remaining = next_deadline - time.perf_counter()
            if remaining > 0:
                time.sleep(remaining)
            else:
                # Overrun: this tick took longer than dt of wall time, so the world runs slower
                # than real time. Usual causes: rendering resolution, NPC count, server quality.
                stats.overruns += 1
                stats.last_overrun_wall = time.perf_counter()
                if remaining < -dt:
                    # WHY: (reset) after a long stall (window drag, GC pause) don't sprint through a
                    # burst of catch-up ticks — that would feel like fast-forward to the driver.
                    next_deadline = time.perf_counter()
        elif loop_time > dt:
            stats.overruns += 1
            stats.last_overrun_wall = time.perf_counter()


def run(cfg: Config) -> int:
    # Heavy imports here so `--help` and config errors don't need carla/pygame installed.
    from carla_rig.control.vehicle import VehicleController
    from carla_rig.output.hud import Hud
    from carla_rig.output.logger import RunLogger
    from carla_rig.sim.session import SimSession

    stats = LoopStats()
    hud = inp = logger = None
    try:
        # HUD first: pygame needs a window before it delivers keyboard events to the input source.
        hud = Hud(cfg.hud)
        inp = make_input_source(cfg.input)
        controller = VehicleController(cfg.control)
        # The `with` guarantees sim cleanup BEFORE the finally below closes the window/logger.
        with SimSession(cfg) as sim:
            logger = RunLogger(cfg)
            if logger.run_dir:
                log.info("logging to %s", logger.run_dir)
            run_loop(cfg, sim, inp, controller, hud, logger, stats)
    finally:
        for name, obj in (("logger", logger), ("input", inp), ("hud", hud)):
            if obj is not None:
                try:
                    obj.close()
                except Exception as exc:  # noqa: BLE001
                    log.warning("closing %s failed: %s", name, exc)
        print("\n=== run summary ===\n" + stats.summary(cfg.world.fixed_delta_seconds))
        if logger is not None and logger.run_dir:
            print(f"log: {logger.run_dir / 'log.csv'} ({logger.rows_written} rows)")
    return 0


def _raise_keyboard_interrupt(signum, frame):  # noqa: ARG001
    # WHY: SIGTERM (e.g. `kill`, a supervisor stopping us) would otherwise exit WITHOUT running
    # finally/__exit__ blocks, leaving the server frozen in sync mode.
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CARLA driving-simulator rig (PoC)")
    parser.add_argument("--config", default="config/default.yaml", help="path to YAML config")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args(argv)

    logging.basicConfig(level=args.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    signal.signal(signal.SIGTERM, _raise_keyboard_interrupt)

    try:
        cfg = load_config(args.config)
    except ConfigError as exc:
        log.error("config error: %s", exc)
        return 2

    try:
        return run(cfg)
    except KeyboardInterrupt:
        log.info("interrupted — cleanup done")
        return 130


if __name__ == "__main__":
    sys.exit(main())
