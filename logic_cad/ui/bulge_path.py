"""LWPOLYLINE bulge tessellation for QPainterPath (DXF mm → scene with Y flip)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainterPath
from ezdxf.math import Vec2, bulge_to_arc

from logic_cad.core.model.constants import WIRE_BULGE_ARC_SEGMENTS


def dxf_to_scene(x: float, y: float) -> QPointF:
    """Map DXF paper coordinates (Y up) to Qt scene (Y down)."""
    return QPointF(x, -y)


def _bulge_sweep_angle(bulge: float) -> float:
    """Return the signed arc sweep angle derived from DXF bulge.

    Args:
        bulge: DXF bulge value on the source segment.

    Returns:
        Signed sweep angle in radians. Positive is CCW, negative is CW.
    """
    return 4.0 * math.atan(float(bulge))


def append_bulge_arc_to_path(
    path: QPainterPath,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    bulge: float,
    *,
    arc_segments: int | None = None,
) -> None:
    """Append the bulge arc from (x0,y0) to chord end (x1,y1) in DXF space to *path* in scene coords.

    The sweep angle is derived from bulge itself to keep orientation stable across
    all quadrants. This avoids angle wrap ambiguity when linearly interpolating
    between two absolute angles around ±pi.

    Args:
        path: Target path (current point must already be at the scene image of (x0,y0)).
        x0: Segment start X in DXF mm.
        y0: Segment start Y in DXF mm.
        x1: Chord end X in DXF mm.
        y1: Chord end Y in DXF mm.
        bulge: DXF bulge on the segment starting at (x0,y0).
        arc_segments: Polyline segments along the arc (default: ``WIRE_BULGE_ARC_SEGMENTS``).
    """
    center, _sa, _ea, r = bulge_to_arc(Vec2(x0, y0), Vec2(x1, y1), bulge)
    cx, cy = float(center.x), float(center.y)
    sa = math.atan2(float(y0) - cy, float(x0) - cx)
    sweep = _bulge_sweep_angle(bulge)
    n = max(8, int(arc_segments if arc_segments is not None else WIRE_BULGE_ARC_SEGMENTS))
    for k in range(1, n + 1):
        t = k / float(n)
        ang = sa + t * sweep
        xd = cx + r * math.cos(ang)
        yd = cy + r * math.sin(ang)
        path.lineTo(dxf_to_scene(xd, yd))
    # Snap the tessellation end point to the exact chord end.
    path.lineTo(dxf_to_scene(float(x1), float(y1)))
