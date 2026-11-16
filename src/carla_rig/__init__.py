"""carla_rig — a layered driving-simulator client for CARLA.

Architecture (data flows left → right, once per simulation tick):

    input/  ──InputState──▶  control/  ──carla.VehicleControl──▶  sim/ (CARLA server)
                                                                     │
    output/ ◀──────────────── VehicleStatus ◀───────────────────────┘

Layers only talk through the dataclasses in ``state.py``. That is what makes it possible to
swap the keyboard for a real wheel by replacing a single ``InputSource`` subclass.
"""

__version__ = "0.1.0"
