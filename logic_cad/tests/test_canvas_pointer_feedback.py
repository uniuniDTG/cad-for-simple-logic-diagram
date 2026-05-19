"""Tests for canvas pointer-feedback diff logic (mouse-move CPU optimizations)."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from logic_cad.ui.items.wire_item import WireItem
from logic_cad.ui.scene_item.osnap import OsnapCandidate
from logic_cad.tests.support.canvas_pointer_feedback import osnap_candidate_key


def test_osnap_candidate_key_stable_for_same_candidate() -> None:
    """Same candidate yields an equal key (skip redundant marker updates)."""
    cand = OsnapCandidate(
        kind="wire_port",
        scene_pos=QPointF(10.0, -20.0),
        dxf_pos=(10.0, 20.0),
        dist_sq_mm=0.1,
        symbol_uid="u1",
        port_key="IN0",
    )
    assert osnap_candidate_key(cand) == osnap_candidate_key(cand)


def test_osnap_candidate_key_differs_when_port_changes() -> None:
    """Port change produces a different key."""
    base = OsnapCandidate(
        kind="wire_port",
        scene_pos=QPointF(0.0, 0.0),
        dxf_pos=(0.0, 0.0),
        dist_sq_mm=0.0,
        symbol_uid="u1",
        port_key="IN0",
    )
    other = OsnapCandidate(
        kind="wire_port",
        scene_pos=QPointF(0.0, 0.0),
        dxf_pos=(0.0, 0.0),
        dist_sq_mm=0.0,
        symbol_uid="u1",
        port_key="OUT0",
    )
    assert osnap_candidate_key(base) != osnap_candidate_key(other)


def test_wire_item_set_hover_segment_skips_redundant_update() -> None:
    """set_hover_segment does not invalidate paint when segment is unchanged."""
    wi = WireItem("wire-test", [], linetype="CONTINUOUS", broken=False)
    wi.set_hover_segment(2)
    assert wi._hover_segment == 2  # noqa: SLF001
    update_count = 0
    original_update = wi.update

    def counting_update() -> None:
        nonlocal update_count
        update_count += 1
        original_update()

    wi.update = counting_update  # type: ignore[method-assign]
    wi.set_hover_segment(2)
    assert update_count == 0
    wi.set_hover_segment(3)
    assert update_count == 1
    assert wi._hover_segment == 3  # noqa: SLF001
