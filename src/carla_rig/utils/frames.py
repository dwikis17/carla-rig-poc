"""Sensor-queue helpers: match sensor data to the simulation tick that produced it.

Role in the architecture
------------------------
CARLA delivers sensor data on a background thread via ``sensor.listen(callback)``. Our callbacks
just ``put()`` each measurement into a ``queue.Queue`` (see ``sim/session.py``). The main loop
then uses these helpers to fetch exactly the measurement that belongs to the frame it just ticked.

Import rules
------------
stdlib only. Works on any object with a ``.frame`` attribute, so it is testable without CARLA.

# WHY frame matching? Even in synchronous mode the camera image for frame N can arrive a few
# milliseconds after ``world.tick()`` returns, and a slow loop can leave older images in the queue.
# Rendering "whatever is at the front of the queue" would show the driver a stale picture that
# lags the physics — nauseating at best, invalid research data at worst.
"""

from __future__ import annotations

import queue
import time
from typing import Any


class FrameTimeoutError(RuntimeError):
    """The sensor did not deliver data for the requested frame in time."""


def wait_for_frame(q: "queue.Queue[Any]", frame: int, timeout: float) -> Any:
    """Return the item from ``q`` whose ``.frame == frame``.

    * Items with an OLDER frame are stale: they are discarded.
    * An item with a NEWER frame means we can never get the one we want (it was dropped),
      so we fail loudly instead of silently rendering the wrong frame.
    * If nothing matching arrives within ``timeout`` seconds, raise ``FrameTimeoutError`` with a
      message that points at the usual causes.
    """
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            item = q.get(timeout=remaining)
        except queue.Empty:
            break
        if item.frame == frame:
            return item
        if item.frame > frame:
            raise FrameTimeoutError(
                f"sensor skipped frame {frame} (got {item.frame}); the sensor tick may not match "
                f"fixed_delta_seconds, or a second client is ticking the world"
            )
        # item.frame < frame → stale, keep draining.
    raise FrameTimeoutError(
        f"no sensor data for frame {frame} within {timeout:.2f}s. Is the server rendering? "
        f"(world.no_rendering_mode must be false; a -RenderOffScreen server still renders cameras.) "
        f"Is another client also calling world.tick()?"
    )


def drain(q: "queue.Queue[Any]") -> list[Any]:
    """Return every item currently in ``q`` without blocking.

    Used for EVENT sensors (collision, lane invasion) that only produce data when something
    happens, so there is nothing to wait for on a normal tick.

    # WHY not frame-match events too? Waiting for an event that may never come would stall every
    # tick. An event that arrives a few ms late is simply reported on the next tick (50 ms later at
    # 20 Hz). RESEARCH: if you need exact event frames, log ``event.frame`` instead of the tick.
    """
    items: list[Any] = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            return items


def clear(q: "queue.Queue[Any]") -> None:
    """Discard everything in ``q`` (e.g. after respawning a sensor)."""
    drain(q)
