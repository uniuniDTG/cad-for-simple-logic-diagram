"""Tests for ``user_line_end_dxf_from_scene`` (sketch + endpoint drag)."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from logic_cad.ui.snap_utils import scene_pos_from_dxf, user_line_end_dxf_from_scene


def test_user_line_end_no_shift_returns_snapped_cursor() -> None:
    p = user_line_end_dxf_from_scene((0.0, 0.0), scene_pos_from_dxf(2.2, 3.1), False)
    assert p == (2.0, 3.0)


def test_user_line_end_shift_prefers_horizontal() -> None:
    """Larger |dx| than |dy| keeps anchor Y (horizontal run from anchor)."""
    anchor = (0.0, 0.0)
    # Snap cursor to (5,1) in DXF: scene (5, -1) => dxf 5,1
    p = user_line_end_dxf_from_scene(anchor, scene_pos_from_dxf(5.0, 1.0), True)
    assert p == (5.0, 0.0)


def test_user_line_end_shift_prefers_vertical() -> None:
    """Larger |dy| than |dx| keeps anchor X."""
    anchor = (0.0, 0.0)
    p = user_line_end_dxf_from_scene(anchor, scene_pos_from_dxf(1.0, 5.0), True)
    assert p == (0.0, 5.0)
