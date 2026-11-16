"""A tiny stand-in for the ``carla`` module, just enough for control/vehicle.py.

conftest.py installs it as ``sys.modules["carla"]`` so the REAL client is never imported by tests
(tests must pass on machines without CARLA installed).
"""

from __future__ import annotations

import enum


class VehicleLightState(enum.IntFlag):
    # Bit values match the real carla.VehicleLightState.
    NONE = 0
    Position = 0x1
    LowBeam = 0x2
    HighBeam = 0x4
    Brake = 0x8
    RightBlinker = 0x10
    LeftBlinker = 0x20
    Reverse = 0x40
    Fog = 0x80
    Interior = 0x100
    Special1 = 0x200
    Special2 = 0x400


class VehicleControl:
    def __init__(self, throttle=0.0, steer=0.0, brake=0.0, hand_brake=False,
                 reverse=False, manual_gear_shift=False, gear=0):
        self.throttle = throttle
        self.steer = steer
        self.brake = brake
        self.hand_brake = hand_brake
        self.reverse = reverse
        self.manual_gear_shift = manual_gear_shift
        self.gear = gear


IS_FAKE = True
