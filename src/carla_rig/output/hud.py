"""HUD: window creation, camera frame display, and driver instruments.

Role in the architecture
------------------------
Pure presentation. Receives the camera image plus ``InputState``/``VehicleStatus`` and draws them.
It never reads input events (the InputSource owns the pygame event queue) and never talks to CARLA
beyond reading the image object it is handed (``.raw_data``, ``.width``, ``.height``).

Draws: camera frame, digital + arc speedometer, flashing blinker arrows (timed by SIM time),
gear (R/D), handbrake, steering bar, controls help (H), red OVERRUN tag.

Import rules
------------
May import ``pygame``, ``numpy``, ``state``, ``config``. Must NOT import ``carla`` or ``input/``.
``bgra_to_rgb`` is numpy-only so it can be tested without a display.

Styling constants below are purely visual (colours, margins). Behavioural tunables (window size,
blink rate, gauge range, font size) come from the ``hud`` section of the config.
"""

from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from carla_rig.config import HudConfig
from carla_rig.state import InputState, VehicleStatus

# --- visual styling (not behavioural tunables) -------------------------------------------------
WHITE = (255, 255, 255)
GREY = (90, 90, 90)
GREEN = (60, 220, 90)
RED = (230, 50, 50)
AMBER = (255, 190, 40)
PANEL = (0, 0, 0, 150)          # translucent black (RGBA) behind instruments
MARGIN = 16
GAUGE_RADIUS = 70
GAUGE_SWEEP_DEG = 240           # classic speedo: 240° sweep, gap at the bottom
STEER_BAR_W, STEER_BAR_H = 240, 10
ARROW_SIZE = 26

HELP_LINES = [
    "W throttle   S brake   A/D steer",
    "Q / E  left / right blinker",
    "Space handbrake (hold)   R reverse",
    "C camera   M mouse steering   H help",
    "Esc quit",
]


def bgra_to_rgb(raw: bytes | memoryview, width: int, height: int) -> np.ndarray:
    """Convert CARLA's BGRA byte buffer to an (H, W, 3) RGB uint8 array — vectorised, no copies
    beyond the one the channel reorder requires.

    # WHY numpy: a per-pixel Python loop over 1280×720 = 921,600 pixels would take ~1 s per frame.
    """
    arr = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 4))
    return arr[:, :, 2::-1]  # B,G,R(,A) → R,G,B : take channels 2,1,0, drop alpha


class Hud:
    """Owns the pygame window and draws one frame per tick."""

    def __init__(self, cfg: HudConfig) -> None:
        import pygame

        self._pg = pygame
        self.cfg = cfg
        pygame.init()
        # SWAP[multi-monitor]: create ONE borderless window spanning all monitors instead of one per
        # screen (multiple pygame windows each flip independently → tearing between screens):
        #     os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"     # before set_mode
        #     size = (monitor_w * n_monitors, monitor_h)
        #     pygame.display.set_mode(size, pygame.NOFRAME)
        # Put the monitors side by side in the OS display settings so the desktop is one wide strip.
        # TUNE: hud.window_width / hud.window_height
        self.screen = pygame.display.set_mode((cfg.window_width, cfg.window_height))
        pygame.display.set_caption(cfg.window_title)
        self.font = pygame.font.SysFont("monospace", cfg.font_size, bold=True)  # TUNE: hud.font_size
        self.big_font = pygame.font.SysFont("monospace", cfg.font_size * 2, bold=True)
        self.show_help = cfg.show_help_on_start
        self._last_surface: Optional[Any] = None
        self._panel = pygame.Surface((cfg.window_width, cfg.window_height), pygame.SRCALPHA)

    # ------------------------------------------------------------------ main entry

    def render(
        self,
        image: Optional[Any],
        inp: InputState,
        status: VehicleStatus,
        camera_view: str,
        overrun: bool,
    ) -> None:
        """Draw everything for this tick. Caller does ``pygame.display.flip()`` (once per frame)."""
        if inp.toggle_help:
            self.show_help = not self.show_help

        self._draw_camera(image)
        self._panel.fill((0, 0, 0, 0))
        self._draw_speedometer(status.speed_kmh)
        self._draw_blinkers(status.blinker, status.sim_time)
        self._draw_status_column(status, inp, camera_view)
        self._draw_steer_bar(status.steer)
        if overrun:
            self._draw_overrun()
        if self.show_help:
            self._draw_help()
        self.screen.blit(self._panel, (0, 0))

    # ------------------------------------------------------------------ pieces

    def _draw_camera(self, image: Optional[Any]) -> None:
        pg = self._pg
        if image is not None:
            rgb = bgra_to_rgb(image.raw_data, image.width, image.height)
            # surfarray expects (W, H, 3), numpy image is (H, W, 3) → swap axes (a view, not a copy).
            surface = pg.surfarray.make_surface(rgb.swapaxes(0, 1))
            if surface.get_size() != self.screen.get_size():
                # TUNE: set camera.width/height == hud.window_* to skip this per-frame scale.
                surface = pg.transform.scale(surface, self.screen.get_size())
            self._last_surface = surface
        # SWAP[multi-monitor]: blit one surface per camera at x = i * monitor_width
        # (all in this same window), then the HUD on the centre screen only.
        if self._last_surface is not None:
            self.screen.blit(self._last_surface, (0, 0))
        else:
            self.screen.fill((0, 0, 0))

    def _draw_speedometer(self, speed_kmh: float) -> None:
        # SWAP[hardware]: a physical speedometer (stepper gauge driven by the Arduino, see
        # input/serial_stalk.py on_vehicle_status) replaces this on-screen gauge.
        pg = self._pg
        w, h = self.screen.get_size()
        cx, cy = w - MARGIN - GAUGE_RADIUS, h - MARGIN - GAUGE_RADIUS
        pg.draw.circle(self._panel, PANEL, (cx, cy), GAUGE_RADIUS + 8)

        # Arc runs from 210° (0 km/h, lower-left) clockwise to -30° (max, lower-right).
        start_deg = 90 + GAUGE_SWEEP_DEG / 2
        frac = max(0.0, min(speed_kmh / self.cfg.gauge_max_kmh, 1.0))  # TUNE: hud.gauge_max_kmh
        rect = pg.Rect(cx - GAUGE_RADIUS, cy - GAUGE_RADIUS, GAUGE_RADIUS * 2, GAUGE_RADIUS * 2)
        end = math.radians(start_deg)
        begin = math.radians(start_deg - GAUGE_SWEEP_DEG)
        pg.draw.arc(self._panel, GREY, rect, begin, end, 6)
        if frac > 0:
            pg.draw.arc(self._panel, GREEN, rect, math.radians(start_deg - GAUGE_SWEEP_DEG * frac), end, 6)

        needle = math.radians(start_deg - GAUGE_SWEEP_DEG * frac)
        tip = (cx + math.cos(needle) * (GAUGE_RADIUS - 12), cy - math.sin(needle) * (GAUGE_RADIUS - 12))
        pg.draw.line(self._panel, RED, (cx, cy), tip, 3)

        txt = self.big_font.render(f"{speed_kmh:3.0f}", True, WHITE)
        self._panel.blit(txt, txt.get_rect(center=(cx, cy + GAUGE_RADIUS // 3)))
        unit = self.font.render("km/h", True, WHITE)
        self._panel.blit(unit, unit.get_rect(center=(cx, cy + GAUGE_RADIUS // 3 + txt.get_height())))

    def _draw_blinkers(self, blinker: str, sim_time: float) -> None:
        pg = self._pg
        # WHY sim time, not wall time: when the loop overruns, sim time slows down with it, so the
        # blink stays consistent with the world (and recordings/replays look right).
        # One full on/off cycle per 1/blink_hz seconds; on for the first half. TUNE: hud.blink_hz
        lit = (sim_time * self.cfg.blink_hz) % 1.0 < 0.5
        w = self.screen.get_width()
        cy = MARGIN + ARROW_SIZE
        for side, cx in (("left", w // 2 - 3 * ARROW_SIZE), ("right", w // 2 + 3 * ARROW_SIZE)):
            d = -1 if side == "left" else 1
            pts = [
                (cx + d * ARROW_SIZE, cy),
                (cx - d * ARROW_SIZE // 2, cy - ARROW_SIZE),
                (cx - d * ARROW_SIZE // 2, cy + ARROW_SIZE),
            ]
            if blinker == side and lit:
                pg.draw.polygon(self._panel, GREEN, pts)
            else:
                pg.draw.polygon(self._panel, GREY, pts, 2)

    def _draw_status_column(self, status: VehicleStatus, inp: InputState, camera_view: str) -> None:
        lines: list[tuple[str, tuple[int, int, int]]] = [
            ("R" if status.reverse else "D", AMBER if status.reverse else WHITE),
            ("HANDBRAKE" if status.hand_brake else "", RED),
            (f"CAM {camera_view}", WHITE),
            ("MOUSE STEER" if inp.mouse_steering else "", AMBER),
            (f"T {status.throttle:4.2f}  B {status.brake:4.2f}", WHITE),
        ]
        if status.collided_this_tick:
            lines.append((f"COLLISION {status.collision_with or ''}", RED))
        if status.lane_invasion:
            lines.append(("LANE INVASION", AMBER))
        y = MARGIN
        for text, colour in lines:
            if text:
                surf = self.font.render(text, True, colour)
                self._panel.blit(surf, (MARGIN, y))
            y += self.font.get_linesize()

    def _draw_steer_bar(self, steer: float) -> None:
        pg = self._pg
        w, h = self.screen.get_size()
        x0 = (w - STEER_BAR_W) // 2
        y0 = h - MARGIN - STEER_BAR_H
        pg.draw.rect(self._panel, PANEL, (x0 - 4, y0 - 4, STEER_BAR_W + 8, STEER_BAR_H + 8))
        pg.draw.rect(self._panel, GREY, (x0, y0, STEER_BAR_W, STEER_BAR_H), 1)
        centre = x0 + STEER_BAR_W // 2
        pg.draw.line(self._panel, GREY, (centre, y0), (centre, y0 + STEER_BAR_H))
        marker = centre + int(steer * STEER_BAR_W / 2)
        pg.draw.rect(self._panel, AMBER, (marker - 3, y0 - 3, 6, STEER_BAR_H + 6))

    def _draw_overrun(self) -> None:
        txt = self.font.render(" OVERRUN ", True, WHITE, RED)
        self._panel.blit(txt, (self.screen.get_width() - txt.get_width() - MARGIN, MARGIN))

    def _draw_help(self) -> None:
        pg = self._pg
        lh = self.font.get_linesize()
        box_w = max(self.font.size(line)[0] for line in HELP_LINES) + 2 * MARGIN
        box_h = lh * len(HELP_LINES) + 2 * MARGIN
        x0 = MARGIN
        y0 = self.screen.get_height() - box_h - MARGIN
        pg.draw.rect(self._panel, PANEL, (x0, y0, box_w, box_h))
        for i, line in enumerate(HELP_LINES):
            self._panel.blit(self.font.render(line, True, WHITE), (x0 + MARGIN, y0 + MARGIN + i * lh))

    def close(self) -> None:
        try:
            self._pg.quit()
        except Exception:  # noqa: BLE001
            pass
