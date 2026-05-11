"""Tests for Escape key handling during block-edit sketch placement."""

from __future__ import annotations

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.services.block_edit_session import BlockEditSession
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.panels.block_edit_panel import BlockEditPanel
from logic_cad.ui.symbol_block_editor.scene import SymbolBlockEditScene


def test_block_edit_escape_cancels_line_preview_then_tool() -> None:
    """First Escape clears in-progress line anchor; second clears placement mode."""

    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    panel = BlockEditPanel(
        lambda: diagram,
        on_applied=lambda: None,
        notify=lambda _msg: None,
    )
    sess = BlockEditSession.open_new("TMP_ESC_TWO_STEP")
    scene = SymbolBlockEditScene(lambda: sess, lambda: None, lambda: "CONTINUOUS")
    panel.attach_scene(scene)
    scene.set_placement_tool("line")
    scene._line_p0_dxf = (0.0, 0.0)

    assert scene.placement_preview_in_progress()
    panel.handle_escape_key()
    assert scene._placement == "line"
    assert scene._line_p0_dxf is None
    assert not scene.placement_preview_in_progress()

    panel.handle_escape_key()
    assert scene._placement is None


def test_block_edit_escape_arc_preview_then_tool() -> None:
    """Arc chord step counts as in-progress preview for the first Escape."""

    ensure_qapplication_offscreen()
    diagram = LogicDiagram.new()
    panel = BlockEditPanel(
        lambda: diagram,
        on_applied=lambda: None,
        notify=lambda _msg: None,
    )
    sess = BlockEditSession.open_new("TMP_ESC_ARC_TWO_STEP")
    scene = SymbolBlockEditScene(lambda: sess, lambda: None, lambda: "CONTINUOUS")
    panel.attach_scene(scene)
    scene.set_placement_tool("arc")
    scene._sketch_arc_dxf_pts.append((1.0, 2.0))

    assert scene.placement_preview_in_progress()
    panel.handle_escape_key()
    assert scene._placement == "arc"
    assert len(scene._sketch_arc_dxf_pts) == 0
    assert not scene.placement_preview_in_progress()

    panel.handle_escape_key()
    assert scene._placement is None
