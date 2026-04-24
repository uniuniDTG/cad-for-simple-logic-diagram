"""Regression tests for ``scene_item.z_order`` and bound ``QGraphicsItem`` Z values."""

from __future__ import annotations

from logic_cad.ui.scene_item.z_order import (
    CANVAS_Z_FRAME_VPORT_PREVIEW,
    CANVAS_Z_PASSIVE_DXF_MIRROR,
    CANVAS_Z_PAPER_LIKE_SYMBOL,
    CANVAS_Z_SYMBOL_AND_WIRE_ARROW,
    CANVAS_Z_USER_CIRCLE,
    CANVAS_Z_USER_CLOUD,
    CANVAS_Z_USER_LINE,
    CANVAS_Z_USER_TEXT,
    CANVAS_Z_WIRE,
)
from logic_cad.ui.items.user_geometry_items import UserLineItem
from logic_cad.ui.items.wire_item import WireItem


def test_canvas_z_constants_strictly_increase_toward_foreground() -> None:
    """Editing-band Z values must stay ordered back-to-front for predictable hit tests."""
    ordered = (
        CANVAS_Z_FRAME_VPORT_PREVIEW,
        CANVAS_Z_PAPER_LIKE_SYMBOL,
        CANVAS_Z_PASSIVE_DXF_MIRROR,
        CANVAS_Z_USER_CLOUD,
        CANVAS_Z_USER_CIRCLE,
        CANVAS_Z_USER_TEXT,
        CANVAS_Z_USER_LINE,
        CANVAS_Z_WIRE,
        CANVAS_Z_SYMBOL_AND_WIRE_ARROW,
    )
    for a, b in zip(ordered[:-1], ordered[1:], strict=True):
        assert a < b


def test_user_line_item_z_matches_constant() -> None:
    """``UserLineItem`` must use :data:`CANVAS_Z_USER_LINE` (not a stray literal)."""
    item = UserLineItem("sk1", 0.0, 0.0, 1.0, 0.0)
    assert item.zValue() == CANVAS_Z_USER_LINE


def test_wire_item_z_matches_constant() -> None:
    """``WireItem`` must use :data:`CANVAS_Z_WIRE`."""
    wire = WireItem("w1", [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0)])
    assert wire.zValue() == CANVAS_Z_WIRE
