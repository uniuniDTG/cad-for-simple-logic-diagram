"""Regression tests for Shift rubber-band selection merge safety."""

from __future__ import annotations

from PySide6.QtWidgets import QGraphicsItem, QGraphicsRectItem, QGraphicsScene

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.views.diagram_view import DiagramView


def test_reapply_shift_rubber_saved_selection_skips_deleted_items() -> None:
    """Deleted Qt items in saved selection are ignored without crashing."""

    ensure_qapplication_offscreen()
    view = DiagramView()
    view.setScene(DiagramScene(LogicDiagram.new()))

    temp_scene = QGraphicsScene()
    deleted_item = QGraphicsRectItem(0.0, 0.0, 1.0, 1.0)
    deleted_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    temp_scene.addItem(deleted_item)
    temp_scene.clear()

    view._shift_rubber_saved = [deleted_item]  # noqa: SLF001
    view._reapply_shift_rubber_saved_selection()  # noqa: SLF001

    assert view._shift_rubber_saved == []  # noqa: SLF001


def test_reapply_shift_rubber_saved_selection_keeps_live_items_selected() -> None:
    """Alive saved items remain selected after reapply."""

    ensure_qapplication_offscreen()
    scene = DiagramScene(LogicDiagram.new())
    view = DiagramView()
    view.setScene(scene)

    live_item = QGraphicsRectItem(0.0, 0.0, 2.0, 2.0)
    live_item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    scene.addItem(live_item)
    live_item.setSelected(False)

    view._shift_rubber_saved = [live_item]  # noqa: SLF001
    view._reapply_shift_rubber_saved_selection()  # noqa: SLF001

    assert live_item.isSelected() is True
    assert view._shift_rubber_saved == [live_item]  # noqa: SLF001
