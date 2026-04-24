"""Tests for passive layout primitives (uid-less DXF entities on the canvas)."""

from __future__ import annotations

from ezdxf.layouts.blocklayout import BlockLayout
from ezdxf.lldxf.tags import Tags
from ezdxf.lldxf.types import DXFTag

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    APPID,
    ENTITY_TYPE_WIRE_ARROW,
    LAYER_ANNOTATION,
    LAYER_CONTENTS_AREA,
    LAYER_FRAME,
    LAYER_PORT,
    LAYER_WIRE_LOGIC,
)
from logic_cad.core.model.layout_entity_layer_policy import is_hidden_for_passive_layout_primitive
from logic_cad.core.model.xdata import build_ld_app_tags, ensure_regapp, get_uid, new_uid, set_entity_xdata
from logic_cad.core.services.pdf_export_service import pdf_export_entity_filter
from logic_cad.ui.passive_dxf_primitives import should_add_passive_primitive


def _layout_block(d: LogicDiagram) -> BlockLayout:
    """Return the block record for the diagram's current paper layout.

    Args:
        d: Open diagram positioned on a paper layout.

    Returns:
        Paper-space ``BlockLayout`` for ``d.current_layout_name``.
    """
    layout = d.doc.layouts.get(d.current_layout_name)
    return d.doc.blocks.get(layout.block_record_name)


def test_should_add_passive_line_without_uid() -> None:
    """Uid-less LINE on a normal layer is eligible for passive display.

    Returns:
        None
    """
    d = LogicDiagram.new()
    blk = _layout_block(d)
    ent = blk.add_line((0, 0), (10, 5), dxfattribs={"layer": LAYER_ANNOTATION})
    assert should_add_passive_primitive(ent)


def test_should_add_false_when_uid_present() -> None:
    """LD_APP uid disqualifies the entity from the passive path.

    Returns:
        None
    """
    d = LogicDiagram.new()
    ensure_regapp(d.doc)
    blk = _layout_block(d)
    ent = blk.add_line((0, 0), (10, 5), dxfattribs={"layer": LAYER_ANNOTATION})
    set_entity_xdata(ent, build_ld_app_tags("1", new_uid(), "USER_LINE"))
    assert not should_add_passive_primitive(ent)


def test_should_add_false_frame_lwpolyline() -> None:
    """Frame/vport polylines are drawn elsewhere; do not duplicate.

    Returns:
        None
    """
    d = LogicDiagram.new()
    blk = _layout_block(d)
    ent = blk.add_lwpolyline([(0, 0), (10, 0)], dxfattribs={"layer": LAYER_FRAME})
    assert not should_add_passive_primitive(ent)


def test_should_add_false_wire_arrow_typed_polyline() -> None:
    """WIRE_ARROW lwpolylines use ``WireArrowItem`` even without a uid.

    Returns:
        None
    """
    d = LogicDiagram.new()
    ensure_regapp(d.doc)
    blk = _layout_block(d)
    ent = blk.add_lwpolyline([(0, 0), (10, 0)], dxfattribs={"layer": LAYER_WIRE_LOGIC})
    ent.set_xdata(APPID, Tags([DXFTag(1000, f"type:{ENTITY_TYPE_WIRE_ARROW}")]))
    assert get_uid(ent) is None
    assert not should_add_passive_primitive(ent)


def test_should_add_false_hidden_layers() -> None:
    """Internal/auxiliary layers match PDF omission policy.

    Returns:
        None
    """
    d = LogicDiagram.new()
    blk = _layout_block(d)
    ent = blk.add_line((0, 0), (10, 5), dxfattribs={"layer": LAYER_PORT})
    assert is_hidden_for_passive_layout_primitive(LAYER_PORT)
    assert not should_add_passive_primitive(ent)
    ent2 = blk.add_line((0, 0), (10, 5), dxfattribs={"layer": LAYER_CONTENTS_AREA})
    assert not should_add_passive_primitive(ent2)


def test_pdf_export_entity_filter_matches_layer_policy() -> None:
    """PDF export filter stays aligned with ``is_hidden_for_passive_layout_primitive``.

    Returns:
        None
    """
    d = LogicDiagram.new()
    blk = _layout_block(d)
    ent = blk.add_line((0, 0), (1, 1), dxfattribs={"layer": LAYER_ANNOTATION})
    assert pdf_export_entity_filter(ent)
    ent2 = blk.add_line((0, 0), (1, 1), dxfattribs={"layer": LAYER_PORT})
    assert not pdf_export_entity_filter(ent2)
