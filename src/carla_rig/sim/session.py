"""CARLA session: connection, synchronous mode, spawning, and GUARANTEED cleanup.

Role in the architecture
------------------------
``SimSession`` is the only place that creates or destroys CARLA actors and the only place that
changes world settings. ``main.py`` uses it as a context manager::

    with SimSession(cfg) as sim:
        ...  # sim.world, sim.vehicle, sim.camera_queue, ...

Import rules
------------
May import ``carla`` and ``config``/``utils``. Must NOT import ``pygame`` or anything from
``input/``/``output/`` — the simulator layer doesn't know how it is being driven or displayed.

# WHY a context manager with guaranteed cleanup?
# In synchronous mode the SERVER WAITS FOR THE CLIENT to call world.tick() before advancing.
# If this client crashes while the world is still in sync mode, the server just sits there frozen,
# and the next client you start appears to hang. Leaked actors (a car parked on the spawn point,
# orphaned sensors still streaming) cause "spawn failed: collision" errors on the next run.
# __exit__ runs on normal exit, Esc, window close, exceptions AND Ctrl+C (KeyboardInterrupt), so
# the server is always left exactly as we found it.
"""

from __future__ import annotations

import logging
import queue
import random
from typing import Any, Optional

import carla  # noqa: F401  (only this layer and control/ may import carla)

from carla_rig.config import CameraMount, Config, ConfigError
from carla_rig.utils.frames import clear

log = logging.getLogger(__name__)


class SimSession:
    """Owns the CARLA client, world settings and every actor this program spawns."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.client: Optional[carla.Client] = None
        self.world: Optional[carla.World] = None
        self.traffic_manager: Optional[Any] = None
        self.vehicle: Optional[carla.Vehicle] = None
        self.camera: Optional[carla.Sensor] = None
        self.collision_sensor: Optional[carla.Sensor] = None
        self.lane_sensor: Optional[carla.Sensor] = None
        self.npcs: list[carla.Actor] = []

        # One queue per sensor. WHY separate queues: frame-matching the camera must not have to
        # skip over collision events, and event sensors are drained without blocking.
        self.camera_queue: "queue.Queue[Any]" = queue.Queue()
        self.collision_queue: "queue.Queue[Any]" = queue.Queue()
        self.lane_queue: "queue.Queue[Any]" = queue.Queue()

        self.camera_view: str = cfg.camera.default_view
        # Bumped whenever the camera is respawned so main.py can tolerate the first missing frame.
        self.camera_generation: int = 0

        self._original_settings: Optional[carla.WorldSettings] = None
        self._tm_sync_enabled = False

    # ------------------------------------------------------------------ lifecycle

    def __enter__(self) -> "SimSession":
        try:
            self._connect()
            self._configure_world()
            self._spawn_ego()
            self._spawn_sensors()
            self._spawn_npcs()
            # One tick so every spawned actor actually exists server-side before the loop starts.
            self.world.tick()
        except BaseException:
            # WHY: __exit__ is NOT called if __enter__ raises, so clean up partial setup here,
            # otherwise a failed spawn would leave the server in sync mode (frozen).
            self.close()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False  # never swallow the exception; we only guarantee cleanup

    # ------------------------------------------------------------------ setup steps

    def _connect(self) -> None:
        s = self.cfg.server
        log.info("connecting to CARLA at %s:%d", s.host, s.port)
        self.client = carla.Client(s.host, s.port)
        self.client.set_timeout(s.timeout_s)  # TUNE: server.timeout_s (big maps load slowly)

        client_v = self.client.get_client_version()
        server_v = self.client.get_server_version()  # first RPC → fails here if server is down
        if client_v != server_v:
            # WHY warn, not abort: dev builds report odd version strings. But a real mismatch causes
            # obscure RPC errors, so make it impossible to miss.
            log.warning("CARLA client %s != server %s — install the matching client wheel!", client_v, server_v)

        w = self.cfg.world
        if w.map:
            log.info("loading map %s", w.map)
            self.world = self.client.load_world(w.map)
        else:
            self.world = self.client.get_world()

    def _configure_world(self) -> None:
        w = self.cfg.world
        # Store the ORIGINAL settings first so close() can always put them back.
        self._original_settings = self.world.get_settings()

        settings = self.world.get_settings()
        # WHY synchronous mode: the server only advances when WE call tick(), so every tick has a
        # known sim-time step, physics is reproducible, and no camera frame is ever skipped.
        settings.synchronous_mode = True
        # TUNE: world.fixed_delta_seconds — simulated time per tick (0.05 = 20 Hz).
        settings.fixed_delta_seconds = w.fixed_delta_seconds
        # WHY substepping: vehicle physics is unstable at 50 ms steps; substeps split each tick into
        # ≤ max_substep_delta_time physics steps. config.validate() already checked
        # fixed_delta_seconds <= max_substep_delta_time * max_substeps.
        settings.substepping = w.substepping
        settings.max_substep_delta_time = w.max_substep_delta_time
        settings.max_substeps = w.max_substeps
        settings.no_rendering_mode = w.no_rendering_mode  # validated False: cameras need rendering
        self.world.apply_settings(settings)

        # Traffic Manager must ALSO be put in sync mode, or NPCs drive on wall-clock time and drift.
        self.traffic_manager = self.client.get_trafficmanager(self.cfg.server.tm_port)
        self.traffic_manager.set_synchronous_mode(True)
        self._tm_sync_enabled = True
        self.traffic_manager.set_random_device_seed(w.seed)  # TUNE: world.seed
        self.traffic_manager.set_hybrid_physics_mode(w.tm_hybrid_physics)

        preset = getattr(carla.WeatherParameters, w.weather, None)
        if not isinstance(preset, carla.WeatherParameters):
            raise ConfigError(f"world.weather: unknown preset {w.weather!r} (see carla.WeatherParameters)")
        self.world.set_weather(preset)
        # RESEARCH: per-trial weather / time-of-day manipulations go here (or in a scenario script).

    def _spawn_ego(self) -> None:
        v = self.cfg.vehicle
        bp_lib = self.world.get_blueprint_library()
        matches = sorted(bp_lib.filter(v.blueprint), key=lambda b: b.id)
        if not matches:
            raise ConfigError(f"vehicle.blueprint: no blueprint matches {v.blueprint!r}")
        bp = matches[0]
        if bp.has_attribute("role_name"):
            bp.set_attribute("role_name", v.role_name)

        spawn_points = self.world.get_map().get_spawn_points()
        if not 0 <= v.spawn_index < len(spawn_points):
            raise ConfigError(f"vehicle.spawn_index {v.spawn_index} out of range (0..{len(spawn_points) - 1})")
        # TUNE: vehicle.spawn_index — pick a start point. RESEARCH: scripted start positions per trial.
        self.vehicle = self.world.spawn_actor(bp, spawn_points[v.spawn_index])
        log.info("spawned ego %s (id=%d) at spawn point %d", bp.id, self.vehicle.id, v.spawn_index)

    def _spawn_sensors(self) -> None:
        self._spawn_camera(self.camera_view)

        bp_lib = self.world.get_blueprint_library()
        self.collision_sensor = self.world.spawn_actor(
            bp_lib.find("sensor.other.collision"), carla.Transform(), attach_to=self.vehicle
        )
        self.collision_sensor.listen(self.collision_queue.put)

        self.lane_sensor = self.world.spawn_actor(
            bp_lib.find("sensor.other.lane_invasion"), carla.Transform(), attach_to=self.vehicle
        )
        self.lane_sensor.listen(self.lane_queue.put)
        # RESEARCH: add more sensors here (e.g. sensor.other.obstacle for distance-to-lead,
        # or a GNSS/IMU for kinematics logging), each with its own queue.

    def _camera_transform(self, view: str) -> "carla.Transform":
        mount: CameraMount = getattr(self.cfg.camera, view)
        # TUNE: camera.chase.* / camera.driver.* (offsets in metres, pitch in degrees)
        return carla.Transform(
            carla.Location(x=mount.x, y=mount.y, z=mount.z),
            carla.Rotation(pitch=mount.pitch),
        )

    def _spawn_camera(self, view: str) -> None:
        c = self.cfg.camera
        bp = self.world.get_blueprint_library().find("sensor.camera.rgb")
        bp.set_attribute("image_size_x", str(c.width))   # TUNE: camera.width
        bp.set_attribute("image_size_y", str(c.height))  # TUNE: camera.height
        bp.set_attribute("fov", str(c.fov))              # TUNE: camera.fov (see formula in default.yaml)
        # sensor_tick 0 = produce an image every simulation tick (required for frame matching).
        bp.set_attribute("sensor_tick", "0.0")

        # SWAP[multi-monitor]: spawn ONE camera per monitor here instead of one. All cameras share
        # the SAME eye location (the driver mount) and differ only in yaw:
        #     yaw_i = (i - center_index) * (fov + bezel_angle)
        # where bezel_angle = the angle the bezel gap subtends from the eye (≈ 2*atan(gap/2/eye_dist)).
        # Give each camera its own queue, set each camera's fov from ITS monitor's width/distance,
        # and wait_for_frame() on every queue each tick. Chase view usually stays single-camera.
        # WHY Rigid attachment: SpringArm smooths motion but lags/jitters in sync mode; for a
        # simulator the view must move exactly with the vehicle.
        self.camera = self.world.spawn_actor(
            bp, self._camera_transform(view), attach_to=self.vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        self.camera.listen(self.camera_queue.put)
        self.camera_view = view
        self.camera_generation += 1

    def _spawn_npcs(self) -> None:
        n = self.cfg.world.npc_vehicles  # TUNE: world.npc_vehicles
        if n <= 0:
            return
        rng = random.Random(self.cfg.world.seed)  # WHY: same seed → same NPC cars at same places
        bp_lib = self.world.get_blueprint_library()
        # Only 4-wheeled cars: bikes/motorbikes behave oddly under the autopilot.
        blueprints = sorted(
            (b for b in bp_lib.filter("vehicle.*")
             if not b.has_attribute("number_of_wheels") or int(b.get_attribute("number_of_wheels")) == 4),
            key=lambda b: b.id,
        )
        points = list(self.world.get_map().get_spawn_points())
        points.pop(self.cfg.vehicle.spawn_index)  # never on top of the ego car
        rng.shuffle(points)

        for transform in points[:n]:
            bp = rng.choice(blueprints)
            if bp.has_attribute("role_name"):
                bp.set_attribute("role_name", "autopilot")
            actor = self.world.try_spawn_actor(bp, transform)  # None if the spot is occupied
            if actor is not None:
                actor.set_autopilot(True, self.cfg.server.tm_port)
                self.npcs.append(actor)
        log.info("spawned %d/%d NPC vehicles", len(self.npcs), n)
        # RESEARCH: replace random traffic with a scripted lead vehicle / ScenarioRunner scenario here.

    # ------------------------------------------------------------------ runtime helpers

    def toggle_camera(self) -> None:
        """Switch between chase and driver view by respawning the camera.

        # WHY respawn instead of moving: set_transform() on an attached sensor is interpreted
        # inconsistently across CARLA versions; destroying and re-attaching is unambiguous.
        # The new camera usually misses the very next frame — main.py tolerates exactly that.
        """
        new_view = "driver" if self.camera_view == "chase" else "chase"
        self._destroy_camera()
        clear(self.camera_queue)
        self._spawn_camera(new_view)

    def _destroy_camera(self) -> None:
        if self.camera is not None:
            try:
                self.camera.stop()
                self.camera.destroy()
            finally:
                self.camera = None

    # ------------------------------------------------------------------ cleanup

    def close(self) -> None:
        """Undo everything, in a safe order. Each step is isolated so one failure can't skip the rest."""

        def safe(what: str, fn) -> None:
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — cleanup must never raise
                log.warning("cleanup: %s failed: %s", what, exc)

        # 1) Stop sensors first so no callbacks fire into half-destroyed state.
        for sensor in (self.camera, self.collision_sensor, self.lane_sensor):
            if sensor is not None:
                safe("stop sensor", sensor.stop)

        # 2) Destroy every actor we spawned (sensors before their parent vehicle).
        actors = [a for a in (self.camera, self.collision_sensor, self.lane_sensor) if a is not None]
        actors += self.npcs
        if self.vehicle is not None:
            actors.append(self.vehicle)
        if self.client is not None and actors:
            # WHY a batch: one RPC instead of N, so cleanup is fast even with many NPCs.
            safe("destroy actors",
                 lambda: self.client.apply_batch_sync([carla.command.DestroyActor(a.id) for a in actors]))
        self.camera = self.collision_sensor = self.lane_sensor = self.vehicle = None
        self.npcs = []

        # 3) Take the Traffic Manager out of sync mode.
        if self.traffic_manager is not None and self._tm_sync_enabled:
            safe("disable TM sync mode", lambda: self.traffic_manager.set_synchronous_mode(False))
            self._tm_sync_enabled = False

        # 4) Restore the original world settings → server leaves sync mode and runs freely again.
        if self.world is not None and self._original_settings is not None:
            safe("restore world settings", lambda: self.world.apply_settings(self._original_settings))
            self._original_settings = None
        log.info("CARLA session cleaned up")
