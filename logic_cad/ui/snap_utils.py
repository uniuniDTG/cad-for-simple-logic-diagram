"""Scene (Qt) vs DXF coordinate snapping."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing import snap_to_grid


def dxf_from_scene_pos(pos: QPointF) -> tuple[float, float]:
    return float(pos.x()), float(-pos.y())


def scene_pos_from_dxf(x: float, y: float) -> QPointF:
    return QPointF(x, -y)


def snap_scene_pos(pos: QPointF, pitch: float = GRID_PITCH) -> QPointF:
    xd, yd = dxf_from_scene_pos(pos)
    sx, sy = snap_to_grid(xd, yd, pitch)
    return scene_pos_from_dxf(sx, sy)


def snap_dxf_pos(x: float, y: float, pitch: float = GRID_PITCH) -> tuple[float, float]:
    return snap_to_grid(x, y, pitch)


def user_line_end_dxf_from_scene(
    anchor_dxf: tuple[float, float], scene_pos: QPointF, shift: bool
) -> tuple[float, float]:
    """Grid-snapped end point for USER_LINE; with Shift, horizontal/vertical from anchor (sketch line tool)."""
    tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos))
    if not shift:
        return (tx, ty)
    ax, ay = float(anchor_dxf[0]), float(anchor_dxf[1])
    dx, dy = tx - ax, ty - ay
    if abs(dx) >= abs(dy):
        return (tx, ay)
    return (ax, ty)


def snap_parallel_drag_delta_mm(raw: float, pitch: float = GRID_PITCH) -> float:
    """Snap a perpendicular drag delta (mm) to an integer number of grid steps.

    Uses round-half-away-from-zero on ``raw / pitch``. Python's built-in
    :func:`round` uses banker's rounding (e.g. ``round(1.5) == 2`` but
    ``round(2.5) == 2``), which can make small drags jump by two grids when
    ``raw`` lands near ``(n + 0.5) * pitch`` due to float noise or unsnapped
    press positions.
    """
    if abs(pitch) < 1e-18:
        return 0.0
    q = raw / pitch
    if q >= 0.0:
        n = math.floor(q + 0.5)
    else:
        n = math.ceil(q - 0.5)
    return n * pitch
