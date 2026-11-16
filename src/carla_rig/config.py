"""Configuration: load ``config/*.yaml`` into typed, validated dataclasses.

Role in the architecture
------------------------
Every other module receives its settings as one of the dataclasses below instead of reading
YAML or holding literals. That gives three things:

1. One place to look for every tunable (``config/default.yaml``).
2. Typos fail fast: unknown keys and wrong types raise ``ConfigError`` at startup, not 10 minutes
   into a participant session.
3. A resolved copy can be saved next to each run's log for reproducibility (``to_dict``).

Import rules
------------
stdlib + ``yaml`` only. Must NOT import ``carla`` or ``pygame`` (tests load configs without them).
"""

from __future__ import annotations

import dataclasses
import math
import typing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


class ConfigError(ValueError):
    """Raised for any invalid configuration (unknown key, wrong type, impossible combination)."""


# ---------------------------------------------------------------------------
# Schema. Defaults mirror config/default.yaml so a partial YAML still works,
# but default.yaml is the documented source of truth.
# ---------------------------------------------------------------------------


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 2000
    timeout_s: float = 10.0
    tm_port: int = 8000


@dataclass
class WorldConfig:
    map: Optional[str] = None
    weather: str = "ClearNoon"
    seed: int = 42
    fixed_delta_seconds: float = 0.05
    realtime_pacing: bool = True
    substepping: bool = True
    max_substep_delta_time: float = 0.01
    max_substeps: int = 10
    no_rendering_mode: bool = False
    npc_vehicles: int = 0
    tm_hybrid_physics: bool = False


@dataclass
class VehicleConfig:
    blueprint: str = "vehicle.tesla.model3"
    role_name: str = "hero"
    spawn_index: int = 0


@dataclass
class CameraMount:
    """Camera offset relative to the vehicle origin (metres, degrees)."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    pitch: float = 0.0


@dataclass
class CameraConfig:
    width: int = 1280
    height: int = 720
    fov: float = 90.0
    default_view: str = "chase"
    chase: CameraMount = field(default_factory=lambda: CameraMount(x=-6.0, z=2.5, pitch=-10.0))
    driver: CameraMount = field(default_factory=lambda: CameraMount(x=0.3, y=-0.35, z=1.25))


@dataclass
class KeyboardConfig:
    throttle_rise_rate: float = 1.5
    throttle_fall_rate: float = 3.0
    brake_rise_rate: float = 2.5
    brake_fall_rate: float = 4.0
    steer_rate: float = 2.0
    steer_return_rate: float = 3.0


@dataclass
class MouseConfig:
    start_enabled: bool = False
    sensitivity: float = 0.003
    centering_rate: float = 0.5


@dataclass
class WheelConfig:
    device_index: int = 0
    steer_axis: int = 0
    throttle_axis: int = 1
    brake_axis: int = 2
    invert_pedals: bool = True
    pedal_deadzone: float = 0.05
    steer_deadzone: float = 0.01
    wheel_range_deg: float = 900.0
    max_steer_angle_deg: float = 450.0


@dataclass
class SerialConfig:
    port: str = "/dev/ttyACM0"
    baudrate: int = 115200
    read_timeout_s: float = 0.05


@dataclass
class InputConfig:
    source: str = "keyboard_mouse"
    keyboard: KeyboardConfig = field(default_factory=KeyboardConfig)
    mouse: MouseConfig = field(default_factory=MouseConfig)
    wheel: WheelConfig = field(default_factory=WheelConfig)
    serial: SerialConfig = field(default_factory=SerialConfig)


@dataclass
class ControlConfig:
    blinker_cancel_arm_threshold: float = 0.35
    blinker_cancel_center_threshold: float = 0.08


@dataclass
class HudConfig:
    window_width: int = 1280
    window_height: int = 720
    window_title: str = "CARLA rig PoC"
    font_size: int = 20
    blink_hz: float = 1.5
    gauge_max_kmh: float = 200.0
    show_help_on_start: bool = True
    overrun_display_s: float = 1.0


@dataclass
class LoggingConfig:
    enabled: bool = True
    output_dir: str = "runs"
    flush_every_n_rows: int = 100
    participant_id: str = ""
    condition: str = ""


@dataclass
class Config:
    server: ServerConfig = field(default_factory=ServerConfig)
    world: WorldConfig = field(default_factory=WorldConfig)
    vehicle: VehicleConfig = field(default_factory=VehicleConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    input: InputConfig = field(default_factory=InputConfig)
    control: ControlConfig = field(default_factory=ControlConfig)
    hud: HudConfig = field(default_factory=HudConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def to_dict(self) -> dict[str, Any]:
        """Plain-dict form, used to save the resolved config next to each run's log."""
        return dataclasses.asdict(self)


# Allowed values for enum-like string fields. Kept here (not in the modules that use them) so
# validation can run without importing pygame/carla.
INPUT_SOURCES = ("keyboard_mouse", "wheel", "serial")
CAMERA_VIEWS = ("chase", "driver")
# CARLA rejects max_substeps outside this range.
MAX_SUBSTEPS_LIMIT = 16


# ---------------------------------------------------------------------------
# Generic dict → dataclass conversion
# ---------------------------------------------------------------------------


def _build(cls: type, data: Any, path: str) -> Any:
    """Recursively turn a dict into dataclass ``cls``, rejecting unknown keys and bad types."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path or 'root'}: expected a mapping, got {type(data).__name__}")

    hints = typing.get_type_hints(cls)
    known = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(f"{path or 'root'}: unknown key(s) {sorted(unknown)}; allowed: {sorted(known)}")

    kwargs: dict[str, Any] = {}
    for name, value in data.items():
        kwargs[name] = _coerce(hints[name], value, f"{path}.{name}" if path else name)
    return cls(**kwargs)


def _coerce(tp: Any, value: Any, path: str) -> Any:
    """Check/convert a single YAML value against its annotated type."""
    if dataclasses.is_dataclass(tp):
        return _build(tp, value, path)

    origin = typing.get_origin(tp)
    if origin is typing.Union:  # Optional[X]
        args = [a for a in typing.get_args(tp) if a is not type(None)]
        if value is None:
            return None
        return _coerce(args[0], value, path)

    # WHY: bool is a subclass of int in Python, so check it explicitly — otherwise
    # `port: true` would silently become port 1.
    if tp is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{path}: expected true/false, got {value!r}")
        return value
    if tp is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{path}: expected an integer, got {value!r}")
        return value
    if tp is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{path}: expected a number, got {value!r}")
        return float(value)
    if tp is str:
        if not isinstance(value, str):
            raise ConfigError(f"{path}: expected a string, got {value!r}")
        return value
    return value


# ---------------------------------------------------------------------------
# Semantic validation (combinations a type check can't catch)
# ---------------------------------------------------------------------------


def validate(cfg: Config) -> None:
    """Raise ConfigError if the config is internally inconsistent."""
    w = cfg.world
    if w.fixed_delta_seconds <= 0:
        # WHY: fixed_delta_seconds = 0 means "variable time step" in CARLA, which breaks
        # determinism and the frame-matching the loop relies on.
        raise ConfigError("world.fixed_delta_seconds must be > 0 (synchronous mode needs a fixed step)")
    if w.substepping:
        if not (1 <= w.max_substeps <= MAX_SUBSTEPS_LIMIT):
            raise ConfigError(f"world.max_substeps must be in [1, {MAX_SUBSTEPS_LIMIT}], got {w.max_substeps}")
        if w.max_substep_delta_time <= 0:
            raise ConfigError("world.max_substep_delta_time must be > 0")
        # WHY: CARLA requires fixed_delta_seconds <= max_substep_delta_time * max_substeps;
        # otherwise physics can't cover a whole tick and the server warns / behaves erratically.
        budget = w.max_substep_delta_time * w.max_substeps
        if w.fixed_delta_seconds > budget + 1e-9:
            raise ConfigError(
                f"world.fixed_delta_seconds ({w.fixed_delta_seconds}) must be <= "
                f"max_substep_delta_time * max_substeps ({w.max_substep_delta_time} * {w.max_substeps} = {budget:.4f})"
            )
    if w.no_rendering_mode:
        raise ConfigError("world.no_rendering_mode must be false: cameras render black frames otherwise")
    if w.npc_vehicles < 0:
        raise ConfigError("world.npc_vehicles must be >= 0")

    if cfg.vehicle.spawn_index < 0:
        raise ConfigError("vehicle.spawn_index must be >= 0")

    c = cfg.camera
    if c.default_view not in CAMERA_VIEWS:
        raise ConfigError(f"camera.default_view must be one of {CAMERA_VIEWS}, got {c.default_view!r}")
    if not (0 < c.fov < 180):
        raise ConfigError(f"camera.fov must be in (0, 180) degrees, got {c.fov}")
    if c.width <= 0 or c.height <= 0:
        raise ConfigError("camera.width/height must be positive")

    if cfg.input.source not in INPUT_SOURCES:
        raise ConfigError(f"input.source must be one of {INPUT_SOURCES}, got {cfg.input.source!r}")
    k = cfg.input.keyboard
    for name in ("throttle_rise_rate", "throttle_fall_rate", "brake_rise_rate",
                 "brake_fall_rate", "steer_rate", "steer_return_rate"):
        if getattr(k, name) <= 0:
            raise ConfigError(f"input.keyboard.{name} must be > 0")
    m = cfg.input.mouse
    if m.sensitivity <= 0:
        raise ConfigError("input.mouse.sensitivity must be > 0")
    if m.centering_rate < 0:
        raise ConfigError("input.mouse.centering_rate must be >= 0 (0 disables the spring)")

    ctl = cfg.control
    if not (0 <= ctl.blinker_cancel_center_threshold < ctl.blinker_cancel_arm_threshold <= 1):
        raise ConfigError(
            "control thresholds must satisfy 0 <= blinker_cancel_center_threshold "
            "< blinker_cancel_arm_threshold <= 1"
        )

    h = cfg.hud
    if h.window_width <= 0 or h.window_height <= 0:
        raise ConfigError("hud.window_width/height must be positive")
    if h.blink_hz <= 0 or h.gauge_max_kmh <= 0 or h.font_size <= 0:
        raise ConfigError("hud.blink_hz, hud.gauge_max_kmh and hud.font_size must be > 0")

    if cfg.logging.flush_every_n_rows < 1:
        raise ConfigError("logging.flush_every_n_rows must be >= 1")

    if not math.isfinite(w.fixed_delta_seconds):
        raise ConfigError("world.fixed_delta_seconds must be finite")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def from_dict(data: dict[str, Any]) -> Config:
    """Build + validate a Config from an already-parsed mapping (handy in tests)."""
    cfg = _build(Config, data, "")
    validate(cfg)
    return cfg


def load_config(path: str | Path) -> Config:
    """Load a YAML file into a validated ``Config``."""
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        try:
            data = yaml.safe_load(fh) or {}
        except yaml.YAMLError as exc:
            raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    return from_dict(data)


def dump_config(cfg: Config, path: str | Path) -> None:
    """Write the resolved config as YAML (used by the logger for reproducibility)."""
    with Path(path).open("w", encoding="utf-8") as fh:
        yaml.safe_dump(cfg.to_dict(), fh, sort_keys=False)
