"""Tests for wire arrow rendering style invariants."""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.items.wire_arrow_item import WireArrowItem


@pytest.mark.parametrize("linetype", ["DASHED", "CENTER", "VALUE"])
def test_wire_arrow_item_pen_is_always_solid(linetype: str) -> None:
    """Wire arrowheads stay solid even when the source wire uses dashed styles."""
    ensure_qapplication_offscreen()
    item = WireArrowItem([(0.0, 0.0), (4.0, 0.0), (3.2, 0.7)], linetype=linetype)

    pen = item.pen()
    assert pen.style() == Qt.PenStyle.SolidLine
    assert pen.dashPattern() == []
