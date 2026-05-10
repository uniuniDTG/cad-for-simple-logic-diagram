"""Tests for USER_ARC in UserGeometryService and block helpers."""

from __future__ import annotations

import math

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_ARC,
    LAYER_SYMBOL,
    LAYER_USER_ARC_CONTINUOUS,
    LINETYPE_CONTINUOUS,
)
from logic_cad.core.model.xdata import get_type
from logic_cad.core.services.block_edit_helpers import add_user_arc_to_block
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.symbol_clipboard import UserSketchCopyRecord
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.tests.support.dxf_layouts import first_paper_layout_name


def test_add_arc_creates_user_arc_on_arc_layer() -> None:
    """add_arc は USER_ARC を ARC として LD_USER_ARC_* に格納する。

    Returns:
        None: アサーションで検証する。
    """
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_arc(
        layout_name,
        (0.0, 0.0),
        10.0,
        0.0,
        90.0,
        LINETYPE_CONTINUOUS,
    )
    e = find_entity_by_uid(doc, uid)
    assert e is not None
    assert e.dxftype() == "ARC"
    assert str(e.dxf.layer) == LAYER_USER_ARC_CONTINUOUS
    assert get_type(e) == ENTITY_TYPE_USER_ARC
    assert abs(float(e.dxf.radius) - 10.0) < 1e-6
    assert abs(float(e.dxf.start_angle) - 0.0) < 1e-6
    assert abs(float(e.dxf.end_angle) - 90.0) < 1e-6


def test_paste_sketch_arc_translates_center() -> None:
    """USER_ARC のクリップボード貼り付けで中心が移動し、角度は維持される。

    Returns:
        None: アサーションで検証する。
    """
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    rec = UserSketchCopyRecord(
        entity_type=ENTITY_TYPE_USER_ARC,
        linetype=LINETYPE_CONTINUOUS,
        arc_center=(1.0, 2.0),
        arc_radius=5.0,
        arc_start_angle_deg=10.0,
        arc_end_angle_deg=80.0,
    )
    uid = svc.paste_sketch_record(layout_name, rec, dx=3.0, dy=-1.0)
    e = find_entity_by_uid(doc, uid)
    assert e is not None and e.dxftype() == "ARC"
    assert abs(float(e.dxf.center.x) - 4.0) < 1e-6
    assert abs(float(e.dxf.center.y) - 1.0) < 1e-6
    assert abs(float(e.dxf.start_angle) - 10.0) < 1e-6
    assert abs(float(e.dxf.end_angle) - 80.0) < 1e-6


def test_add_user_arc_to_block_tags_layer_symbol() -> None:
    """ブロック編集の USER_ARC は他のブロック内ユーザジオメトリ同様 LD_SYMBOL 上にある。

    Returns:
        None: アサーションで検証する。
    """
    doc = new_document()
    blk = doc.blocks.new("TEST_ARC_BLK")
    uid = add_user_arc_to_block(blk, (0.0, 0.0), 4.0, 0.0, 180.0, "CONTINUOUS")
    e = find_entity_by_uid(doc, uid)
    assert e is not None
    assert e.dxftype() == "ARC"
    assert str(e.dxf.layer) == LAYER_SYMBOL
    assert get_type(e) == ENTITY_TYPE_USER_ARC
    assert math.isclose(float(e.dxf.radius), 4.0)
