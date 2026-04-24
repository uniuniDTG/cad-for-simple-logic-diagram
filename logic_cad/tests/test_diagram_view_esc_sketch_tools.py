"""Esc on DiagramView: cancel in-progress sketch without clearing tool; second Esc clears tool.

Regression tests for two-step Esc: first clears partial geometry only, second clears sketch
toolbar state via the view callback.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.views.diagram_view import DiagramView


def _send_escape(view: DiagramView) -> None:
    """Deliver a KeyPress Esc to the view as Qt would.

    Args:
        view: Target diagram view.

    Returns:
        None
    """
    ev = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)
    view.keyPressEvent(ev)


def test_user_sketch_has_in_progress_geometry_line_first_point() -> None:
    """Partial line (p0 set) is in-progress; idle line tool is not.

    Args:
        None

    Returns:
        None
    """
    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    scene = DiagramScene(diagram)
    scene.set_user_sketch_tool("line")
    assert scene.user_sketch_has_in_progress_geometry() is False
    scene._sketch_p0_dxf = (10.0, 20.0)  # noqa: SLF001 — mirror first-click state
    assert scene.user_sketch_has_in_progress_geometry() is True


def test_user_sketch_has_in_progress_geometry_cloud_vertex() -> None:
    """Cloud with at least one stored vertex counts as in-progress.

    Args:
        None

    Returns:
        None
    """
    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    scene = DiagramScene(diagram)
    scene.set_user_sketch_tool("cloud")
    scene._sketch_cloud_vertices_dxf.append((1.0, 2.0))  # noqa: SLF001
    assert scene.user_sketch_has_in_progress_geometry() is True


def test_esc_twice_sketch_tool_first_cancels_geometry_only() -> None:
    """First Esc clears partial sketch; second Esc invokes sketch-tool clear callback.

    Args:
        None

    Returns:
        None
    """
    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    scene = DiagramScene(diagram)
    scene.set_user_sketch_tool("line")
    scene._sketch_p0_dxf = (10.0, 20.0)  # noqa: SLF001

    clear_sketch_calls: list[int] = []

    def mock_uncheck_sketch_tools() -> None:
        clear_sketch_calls.append(1)
        scene.set_user_sketch_tool("none")

    view = DiagramView()
    view.setScene(scene)
    view.set_escape_clear_sketch_tools_callback(mock_uncheck_sketch_tools)
    view.setFocus()

    _send_escape(view)
    assert clear_sketch_calls == []
    assert scene.user_sketch_tool() == "line"
    assert scene.user_sketch_has_in_progress_geometry() is False

    _send_escape(view)
    assert clear_sketch_calls == [1]
    assert scene.user_sketch_tool() == "none"
