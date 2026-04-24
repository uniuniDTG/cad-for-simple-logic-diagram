"""Default linetype for the line sketch tool (toolbar / scene state)."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.scene import DiagramScene


def test_user_sketch_line_default_linetype_initial_continuous() -> None:
    """New scene defaults to CONTINUOUS for the next user line.

    Args:
        None

    Returns:
        None
    """
    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    scene = DiagramScene(diagram)
    assert scene.user_sketch_line_default_linetype() == "CONTINUOUS"


def test_set_user_sketch_line_default_linetype_normalizes() -> None:
    """Setter maps aliases to CONTINUOUS / DASHED / CENTER.

    Args:
        None

    Returns:
        None
    """
    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    scene = DiagramScene(diagram)
    scene.set_user_sketch_line_default_linetype("DASHED")
    assert scene.user_sketch_line_default_linetype() == "DASHED"
    scene.set_user_sketch_line_default_linetype("CENTER")
    assert scene.user_sketch_line_default_linetype() == "CENTER"
    scene.set_user_sketch_line_default_linetype("  continuous  ")
    assert scene.user_sketch_line_default_linetype() == "CONTINUOUS"
