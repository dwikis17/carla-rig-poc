"""Smoke test: run the real main loop + HUD for a few ticks against a FAKE sim, headless.

Catches wiring mistakes (wrong attribute names, step order, HUD drawing errors) without CARLA.
Uses SDL's dummy video driver so no window opens.
"""

import queue
from types import SimpleNamespace

import pytest

pygame = pytest.importorskip("pygame")

from carla_rig.config import from_dict  # noqa: E402
from carla_rig.control.vehicle import VehicleController  # noqa: E402
from carla_rig.input.base import InputSource  # noqa: E402
from carla_rig.main import LoopStats, run_loop  # noqa: E402
from carla_rig.output.logger import RunLogger  # noqa: E402
from carla_rig.state import InputState  # noqa: E402

W, H = 64, 48


class FakeImage:
    def __init__(self, frame):
        self.frame, self.width, self.height = frame, W, H
        self.raw_data = bytes(W * H * 4)


class FakeVehicle:
    id = 1

    def apply_control(self, c):
        self.last = c

    def get_light_state(self):
        return 0

    def set_light_state(self, s):
        pass


class FakeWorld:
    def __init__(self, sim):
        self.sim, self.frame = sim, 0

    def tick(self):
        self.frame += 1
        self.sim.camera_queue.put(FakeImage(self.frame))
        if self.frame == 2:
            self.sim.collision_queue.put(SimpleNamespace(frame=2, other_actor=SimpleNamespace(type_id="static.wall")))
        return self.frame

    def get_snapshot(self):
        v = SimpleNamespace(x=10 / 3.6, y=0.0, z=0.0)  # 10 km/h
        tf = SimpleNamespace(location=SimpleNamespace(x=1.0, y=2.0, z=0.0), rotation=SimpleNamespace(yaw=90.0))
        actor = SimpleNamespace(get_transform=lambda: tf, get_velocity=lambda: v)
        return SimpleNamespace(
            frame=self.frame,
            timestamp=SimpleNamespace(elapsed_seconds=self.frame * 0.05),
            find=lambda _id: actor,
        )


class FakeSim:
    def __init__(self):
        self.camera_queue, self.collision_queue, self.lane_queue = queue.Queue(), queue.Queue(), queue.Queue()
        self.vehicle = FakeVehicle()
        self.world = FakeWorld(self)
        self.camera_view = "chase"
        self.camera_generation = 1
        self.toggles = 0

    def toggle_camera(self):
        self.toggles += 1
        self.camera_view = "driver"


class ScriptedInput(InputSource):
    def __init__(self, n_ticks):
        self.n, self.i, self.statuses = n_ticks, 0, []

    def update(self, dt):
        self.i += 1
        return InputState(throttle=0.5, blinker="left", toggle_camera=self.i == 1,
                          toggle_help=self.i == 2, quit=self.i > self.n)

    def on_vehicle_status(self, status):
        self.statuses.append(status)


def test_main_loop_runs_headless(tmp_path, monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    monkeypatch.setenv("SDL_AUDIODRIVER", "dummy")
    from carla_rig.output.hud import Hud

    cfg = from_dict({
        "world": {"realtime_pacing": False},
        "camera": {"width": W, "height": H},
        "hud": {"window_width": W * 2, "window_height": H * 2},  # forces the scale path
        "logging": {"output_dir": str(tmp_path), "flush_every_n_rows": 2},
    })
    sim, inp = FakeSim(), ScriptedInput(n_ticks=4)
    hud = Hud(cfg.hud)
    logger = RunLogger(cfg)
    stats = LoopStats()
    try:
        run_loop(cfg, sim, inp, VehicleController(cfg.control), hud, logger, stats)
    finally:
        logger.close()
        hud.close()

    assert stats.ticks == 4
    assert sim.toggles == 1
    assert [s.frame for s in inp.statuses] == [1, 2, 3, 4]
    assert inp.statuses[0].speed_kmh == pytest.approx(10.0)
    assert inp.statuses[1].collided_this_tick and inp.statuses[1].collision_with == "static.wall"
    assert not inp.statuses[2].collided_this_tick
    assert logger.rows_written == 4
    assert "overruns=" in stats.summary(cfg.world.fixed_delta_seconds)
