"""Tests for wire parallel-drag delta snapping (scene / snap_utils)."""

from __future__ import annotations

from logic_cad.ui.snap_utils import snap_parallel_drag_delta_mm


def test_snap_parallel_drag_delta_half_away_from_zero() -> None:
    pitch = 1.0
    assert snap_parallel_drag_delta_mm(1.4, pitch) == 1.0
    assert snap_parallel_drag_delta_mm(1.5, pitch) == 2.0
    assert snap_parallel_drag_delta_mm(1.6, pitch) == 2.0
    assert snap_parallel_drag_delta_mm(2.5, pitch) == 3.0
    assert snap_parallel_drag_delta_mm(-1.5, pitch) == -2.0
    assert snap_parallel_drag_delta_mm(-0.6, pitch) == -1.0
