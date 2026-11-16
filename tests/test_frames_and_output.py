"""Frame matching, CSV logger and BGRA conversion — all without CARLA or a display."""

import csv
import queue
from dataclasses import dataclass

import numpy as np
import pytest

from carla_rig.config import from_dict
from carla_rig.output.hud import bgra_to_rgb
from carla_rig.output.logger import RunLogger, csv_columns
from carla_rig.state import InputState, VehicleStatus
from carla_rig.utils.frames import FrameTimeoutError, drain, wait_for_frame


@dataclass
class Item:
    frame: int


# --- frames ---------------------------------------------------------------------------------

def test_wait_for_frame_drains_stale():
    q = queue.Queue()
    for f in (8, 9, 10):
        q.put(Item(f))
    assert wait_for_frame(q, 10, timeout=0.1).frame == 10
    assert q.empty()


def test_wait_for_frame_times_out():
    q = queue.Queue()
    q.put(Item(3))
    with pytest.raises(FrameTimeoutError, match="frame 5"):
        wait_for_frame(q, 5, timeout=0.05)


def test_wait_for_frame_newer_frame_raises():
    q = queue.Queue()
    q.put(Item(12))
    with pytest.raises(FrameTimeoutError, match="skipped"):
        wait_for_frame(q, 10, timeout=0.1)


def test_drain_returns_all_without_blocking():
    q = queue.Queue()
    for f in range(3):
        q.put(Item(f))
    assert [i.frame for i in drain(q)] == [0, 1, 2]
    assert drain(q) == []


# --- logger ---------------------------------------------------------------------------------

def make_status(frame):
    return VehicleStatus(frame=frame, sim_time=frame * 0.05, speed_kmh=10.0, x=1, y=2, z=0, yaw=90,
                         throttle=0.5, brake=0.0, steer=0.1, blinker="left", hand_brake=False, reverse=False)


def test_logger_buffers_and_writes(tmp_path):
    cfg = from_dict({"logging": {"output_dir": str(tmp_path), "flush_every_n_rows": 3, "participant_id": "P01"}})
    logger = RunLogger(cfg)
    log_path = logger.run_dir / "log.csv"

    for f in range(2):
        logger.write(make_status(f), InputState(throttle=0.5))
    assert len(log_path.read_text().splitlines()) == 1  # header only: still buffered

    logger.write(make_status(2), InputState())
    assert len(log_path.read_text().splitlines()) == 4  # flushed at N=3

    logger.write(make_status(3), InputState())
    logger.close()
    rows = list(csv.DictReader(log_path.open()))
    assert len(rows) == 4
    assert list(rows[0].keys()) == csv_columns()
    assert rows[0]["participant_id"] == "P01" and rows[3]["frame"] == "3"
    assert (logger.run_dir / "config.yaml").is_file()


def test_logger_disabled_writes_nothing(tmp_path):
    cfg = from_dict({"logging": {"enabled": False, "output_dir": str(tmp_path)}})
    logger = RunLogger(cfg)
    logger.write(make_status(0), InputState())
    logger.close()
    assert list(tmp_path.iterdir()) == []


# --- HUD image conversion ---------------------------------------------------------------------

def test_bgra_to_rgb():
    # 1×2 image: pixel0 = B10 G20 R30 A255, pixel1 = B1 G2 R3 A0
    raw = bytes([10, 20, 30, 255, 1, 2, 3, 0])
    rgb = bgra_to_rgb(raw, width=2, height=1)
    assert rgb.shape == (1, 2, 3)
    np.testing.assert_array_equal(rgb[0, 0], [30, 20, 10])
    np.testing.assert_array_equal(rgb[0, 1], [3, 2, 1])
