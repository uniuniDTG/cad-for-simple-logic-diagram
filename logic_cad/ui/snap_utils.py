"""Scene (Qt) vs DXF coordinate snapping."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF
from PySide6.QtWidgets import QGraphicsItem

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing import snap_to_grid


def snap_pitch_for_qgraphics_item(item: QGraphicsItem) -> float:
    """Return the DXF snap pitch (mm) for ``item`` based on its parent scene.

    Scenes that define ``snap_pitch_mm`` (e.g. block definition editor) use a finer
    step; otherwise the main canvas pitch :data:`~logic_cad.core.model.constants.GRID_PITCH`
    applies.

    Args:
        item: Graphics item that may belong to a scene with ``snap_pitch_mm``.

    Returns:
        Grid step in millimetres for snapping item positions in scene coordinates.
    """
    sc = item.scene()
    if sc is None:
        return GRID_PITCH
    return float(getattr(sc, "snap_pitch_mm", GRID_PITCH))


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
    anchor_dxf: tuple[float, float],
    scene_pos: QPointF,
    shift: bool,
    *,
    pitch: float = GRID_PITCH,
) -> tuple[float, float]:
    """Grid-snapped end point for USER_LINE; with Shift, horizontal/vertical from anchor (sketch line tool).

    Args:
        anchor_dxf: Fixed endpoint in DXF mm when Shift-constraining the other leg.
        scene_pos: Cursor position in scene coordinates.
        shift: If True, snap to horizontal or vertical from ``anchor_dxf``.
        pitch: Grid step in mm (block editor uses a finer pitch than the main canvas).

    Returns:
        Snapped ``(x, y)`` in DXF mm.
    """
    tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos), pitch=pitch)
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
