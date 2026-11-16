"""STUB: Arduino turn-signal stalk / buttons over a serial port (``pyserial``).

Role in the architecture
------------------------
Provides the controls a game wheel doesn't have: a real turn-signal stalk, horn, hazard, ignition.
Can be used alone (``input.source: serial`` — useful for bench-testing the Arduino) but is normally
merged INTO ``WheelInput`` so ``main.py`` still sees a single InputSource.

Import rules
------------
May import ``serial`` (pyserial), ``threading``, ``queue``, ``state``, ``config``, ``input.base``.
Must NOT import ``carla`` or ``pygame``.

# SWAP[hardware]: implement this class for the physical stalk / button box.

Suggested wire protocol (Arduino → PC), one ASCII line per change, newline-terminated
-------------------------------------------------------------------------------------
    TURN:L\\n      left signal on          TURN:R\\n     right signal on
    TURN:OFF\\n    stalk back in centre    HORN:1\\n     horn pressed / HORN:0\\n released
    HAZARD:1\\n    hazard switch on        HB:1\\n       handbrake button (HB:0 released)
    HELLO:<fw-version>\\n                  sent once on boot — lets you check you opened the right port

Why this shape: human-readable (debug with the Arduino IDE serial monitor), trivially parsed with
``line.split(":", 1)``, robust to a lost byte (the next newline resynchronises), and STATE-based
rather than toggle-based — if one line is lost, the next state change corrects it. Have the
Arduino also re-send its full state every ~500 ms as a heartbeat so a reconnect self-heals.
Debounce switches on the Arduino side (~20 ms), not in Python.

Mechanical self-cancel
    A real stalk cancels itself mechanically and then sends TURN:OFF. In that case disable the
    software auto-cancel in control/vehicle.py (set blinker_cancel_arm_threshold to 1.0) so the
    two don't fight.

Threading — serial I/O must never block the sim loop
----------------------------------------------------
``serial.Serial.readline()`` blocks until a newline or timeout. Doing that inside the 50 ms tick
would cause overruns. Instead:

    def __init__(...):
        self._ser = serial.Serial(cfg.serial.port, cfg.serial.baudrate,
                                  timeout=cfg.serial.read_timeout_s)
        self._latest = {"TURN": "OFF", "HORN": "0", "HB": "0"}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):                      # background thread
        while not self._stop.is_set():
            line = self._ser.readline().decode("ascii", "ignore").strip()
            if ":" in line:
                key, value = line.split(":", 1)
                with self._lock:
                    self._latest[key] = value

    def update(self, dt):                   # sim thread: just copies the latest snapshot
        with self._lock:
            turn = self._latest["TURN"]
        blinker = {"L": "left", "R": "right"}.get(turn, "off")
        return InputState(blinker=blinker, hand_brake=self._latest["HB"] == "1")

    def close(self):
        self._stop.set(); self._thread.join(timeout=1); self._ser.close()

``daemon=True`` means a crash can't leave the process hanging on the reader thread. Expect the
Arduino to RESET when the port opens (DTR line); wait for its HELLO line before trusting data.

Physical gauges (PC → Arduino)
    The same port can carry output: write ``SPD:<kmh>\\n`` from ``on_vehicle_status()`` to drive a
    stepper-motor speedometer. Rate-limit to ~20 Hz and use a separate write lock.
"""

from __future__ import annotations

from carla_rig.config import InputConfig
from carla_rig.input.base import InputSource
from carla_rig.state import InputState, VehicleStatus


class SerialStalkInput(InputSource):
    """Arduino stalk / button box. NOT IMPLEMENTED — see the module docstring for the recipe."""

    def __init__(self, cfg: InputConfig) -> None:
        # SWAP[hardware]: open the port and start the background reader thread here.
        self._cfg = cfg.serial

    def update(self, dt: float) -> InputState:
        # SWAP[hardware]: return InputState built from the latest thread-updated snapshot.
        # When used standalone (input.source: serial) there is no throttle/steer, which is fine for
        # bench-testing the stalk but you'll also need to pump pygame events for Esc/window close.
        raise NotImplementedError(
            "SerialStalkInput is a stub. Implement it (see src/carla_rig/input/serial_stalk.py "
            "docstring) or set input.source: keyboard_mouse in your config."
        )

    def on_vehicle_status(self, status: VehicleStatus) -> None:
        # SWAP[hardware]: physical speedometer — write f"SPD:{status.speed_kmh:.0f}\n" to the port
        # (rate-limited) instead of / in addition to the on-screen gauge in output/hud.py.
        pass

    def close(self) -> None:
        # SWAP[hardware]: stop the thread, join it, close the port. Must be idempotent.
        pass
