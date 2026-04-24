"""Tests for USER_CLOUD behavior in UserGeometryService."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.pages.page_order import list_paper_layout_names_sorted
from logic_cad.core.model.cloud_guide_xdata import (
    build_cloud_pitch_xdata_extra,
    parse_cloud_guide_vertices,
    parse_cloud_segment_mm,
)
from logic_cad.core.model.constants import (
    ENTITY_TYPE_USER_CLOUD,
    LAYER_USER_CLOUD_CONTINUOUS,
    USER_CLOUD_BULGE,
    LINETYPE_CONTINUOUS,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, read_ld_app_dict, set_entity_xdata
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.tests.support.dxf_layouts import first_paper_layout_name


def _count_user_cloud_entities(doc: Drawing) -> int:
    """Count USER_CLOUD LWPOLYLINE entities on all paper layouts."""
    n = 0
    for layout_name in list_paper_layout_names_sorted(doc):
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        for e in blk:
            if e.dxftype() == "LWPOLYLINE" and get_type(e) == ENTITY_TYPE_USER_CLOUD:
                n += 1
    return n


def test_add_cloud_creates_user_cloud_on_cloud_layer() -> None:
    """add_cloud stores USER_CLOUD as an LWPOLYLINE on LD_USER_CLOUD_*."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    entity = find_entity_by_uid(doc, uid)

    assert entity is not None
    assert entity.dxftype() == "LWPOLYLINE"
    assert str(entity.dxf.layer) == LAYER_USER_CLOUD_CONTINUOUS
    assert bool(entity.closed) is True
    assert get_type(entity) == ENTITY_TYPE_USER_CLOUD
    widths = [(float(r[2]), float(r[3])) for r in entity.get_points("xyseb")]
    assert all(abs(sw) < 1e-9 and abs(ew) < 1e-9 for sw, ew in widths)
    bulges = [float(r[2]) if len(r) > 2 else 0.0 for r in entity.get_points("xyb")]
    assert any(abs(abs(b) - USER_CLOUD_BULGE) < 1e-6 for b in bulges)


def test_add_cloud_closed_ccw_positive_bulge_cw_negative() -> None:
    """Closed clouds use winding-signed bulge: CCW → positive, CW → negative."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    ccw_rect = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    uid_ccw = svc.add_cloud(
        layout_name,
        ccw_rect,
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    ent_ccw = find_entity_by_uid(doc, uid_ccw)
    assert ent_ccw is not None
    bulges_ccw = [float(r[2]) if len(r) > 2 else 0.0 for r in ent_ccw.get_points("xyb")]
    nonzero_ccw = [b for b in bulges_ccw if abs(b) > 1e-9]
    assert nonzero_ccw
    assert all(b > 0.0 for b in nonzero_ccw)

    cw_rect = [(0.0, 0.0), (0.0, 6.0), (12.0, 6.0), (12.0, 0.0)]
    uid_cw = svc.add_cloud(
        layout_name,
        cw_rect,
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    ent_cw = find_entity_by_uid(doc, uid_cw)
    assert ent_cw is not None
    bulges_cw = [float(r[2]) if len(r) > 2 else 0.0 for r in ent_cw.get_points("xyb")]
    nonzero_cw = [b for b in bulges_cw if abs(b) > 1e-9]
    assert nonzero_cw
    assert all(b < 0.0 for b in nonzero_cw)
    assert any(abs(abs(b) - USER_CLOUD_BULGE) < 1e-6 for b in bulges_cw)


def test_add_cloud_open_path_remains_open() -> None:
    """add_cloud supports open-path clouds (non-closed revision marks)."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (8.0, 0.0), (8.0, 8.0), (0.0, 8.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=False,
    )

    entity = find_entity_by_uid(doc, uid)
    assert entity is not None
    assert bool(entity.closed) is False
    bulges = [float(r[2]) if len(r) > 2 else 0.0 for r in entity.get_points("xyb")]
    assert any(abs(abs(b) - USER_CLOUD_BULGE) < 1e-6 for b in bulges[:-1])
    pts = [(float(r[0]), float(r[1])) for r in entity.get_points("xyb")]
    assert pts
    start = pts[0]
    end = pts[-1]
    # Open cloud should end near the final user vertex, not loop back to start.
    assert abs(end[0] - 0.0) > 1.0 or abs(end[1] - 0.0) > 1.0
    assert abs(end[0] - start[0]) > 1.0 or abs(end[1] - start[1]) > 1.0


def test_add_cloud_open_two_point_path_supported() -> None:
    """A two-point open path is accepted and stays open."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (12.0, 0.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=False,
    )
    entity = find_entity_by_uid(doc, uid)
    assert entity is not None
    assert bool(entity.closed) is False
    assert len(list(entity.get_points("xyb"))) >= 2


def test_clipboard_record_and_paste_preserve_cloud_shape() -> None:
    """clipboard_record_for_uid and paste_sketch_record keep cloud points and closed state."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=False,
    )
    rec = svc.clipboard_record_for_uid(uid)
    assert rec is not None
    assert rec.entity_type == ENTITY_TYPE_USER_CLOUD
    assert rec.cloud_points_xyb
    assert rec.cloud_is_closed is False

    pasted_uid = svc.paste_sketch_record(layout_name, rec, dx=20.0, dy=10.0)
    pasted = find_entity_by_uid(doc, pasted_uid)
    assert pasted is not None
    assert pasted.dxftype() == "LWPOLYLINE"
    assert bool(pasted.closed) is False
    assert len(list(pasted.get_points("xyb"))) == len(rec.cloud_points_xyb)


def test_add_cloud_stores_pitch_and_guides_in_xdata() -> None:
    """New clouds persist cloud_seg and guide vertices in LD_APP."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    guide = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    uid = svc.add_cloud(
        layout_name,
        guide,
        segment_length=1.25,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    e = find_entity_by_uid(doc, uid)
    assert e is not None
    xd = read_ld_app_dict(e)
    assert parse_cloud_segment_mm(xd) == 1.25
    gv = parse_cloud_guide_vertices(xd)
    assert gv is not None
    assert len(gv) == 4
    assert abs(gv[0][0] - 0.0) < 1e-5


def test_set_user_cloud_pitch_mm_changes_vertex_count() -> None:
    """Increasing pitch reduces tessellation density (fewer LW vertices)."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (30.0, 0.0), (30.0, 20.0), (0.0, 20.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    ent0 = find_entity_by_uid(doc, uid)
    assert ent0 is not None
    n0 = len(list(ent0.get_points("xyb")))
    assert svc.set_user_cloud_pitch_mm(uid, 8.0) is True
    ent1 = find_entity_by_uid(doc, uid)
    assert ent1 is not None
    n1 = len(list(ent1.get_points("xyb")))
    assert n1 < n0
    assert parse_cloud_segment_mm(read_ld_app_dict(ent1)) == 8.0


def test_legacy_cloud_without_pitch_xdata_gets_guides_on_first_pitch_apply() -> None:
    """Stripping pitch XDATA still allows pitch apply via inferred guides."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (20.0, 0.0), (20.0, 12.0), (0.0, 12.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    e = find_entity_by_uid(doc, uid)
    assert e is not None
    d = read_ld_app_dict(e)
    set_entity_xdata(
        e,
        build_ld_app_tags(str(d.get("ver", "1")), str(d["uid"]), ENTITY_TYPE_USER_CLOUD, None),
    )
    assert parse_cloud_guide_vertices(read_ld_app_dict(e)) is None
    assert svc.set_user_cloud_pitch_mm(uid, 3.0) is True
    xd2 = read_ld_app_dict(find_entity_by_uid(doc, uid))
    assert parse_cloud_segment_mm(xd2) == 3.0
    assert parse_cloud_guide_vertices(xd2) is not None


def test_set_user_cloud_geometry_translates_stored_guides() -> None:
    """Moving the cloud outline translates guide vertices in XDATA."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (15.0, 0.0), (15.0, 9.0), (0.0, 9.0)],
        segment_length=2.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    e = find_entity_by_uid(doc, uid)
    assert e is not None
    g0 = parse_cloud_guide_vertices(read_ld_app_dict(e))
    assert g0 is not None
    rows = list(e.get_points("xyb"))
    shifted = [(float(x) + 7.0, float(y) + 4.0, float(b)) for x, y, b in rows]
    assert svc.set_user_cloud_geometry(uid, shifted, is_closed=True) is True
    e2 = find_entity_by_uid(doc, uid)
    assert e2 is not None
    g1 = parse_cloud_guide_vertices(read_ld_app_dict(e2))
    assert g1 is not None
    assert abs(g1[0][0] - (g0[0][0] + 7.0)) < 1e-5
    assert abs(g1[0][1] - (g0[0][1] + 4.0)) < 1e-5


def test_cloud_guide_xdata_chunk_roundtrip() -> None:
    """Long JSON payloads split across cloud_path_* keys and decode correctly."""
    many = [(float(i), float(i) * 0.25) for i in range(90)]
    extra = build_cloud_pitch_xdata_extra(4.0, many)
    assert "cloud_path_1" in extra
    xd = {**extra}
    assert parse_cloud_segment_mm(xd) == 4.0
    back = parse_cloud_guide_vertices(xd)
    assert back is not None
    assert len(back) == 90


def test_clipboard_preserves_cloud_pitch_and_guides() -> None:
    """Copy/paste keeps cloud_seg and guide vertices when present."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)],
        segment_length=2.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=False,
    )
    rec = svc.clipboard_record_for_uid(uid)
    assert rec is not None
    assert rec.cloud_pitch_mm == 2.0
    assert rec.cloud_guide_vertices is not None
    assert len(rec.cloud_guide_vertices) >= 2

    pasted_uid = svc.paste_sketch_record(layout_name, rec, dx=100.0, dy=0.0)
    pe = find_entity_by_uid(doc, pasted_uid)
    assert pe is not None
    xd = read_ld_app_dict(pe)
    assert parse_cloud_segment_mm(xd) == 2.0
    gv = parse_cloud_guide_vertices(xd)
    assert gv is not None
    assert abs(gv[0][0] - 100.0) < 0.01


def test_delete_all_user_clouds_all_pages_removes_across_layouts() -> None:
    """Bulk delete removes clouds on every paper layout."""
    d = LogicDiagram.new()
    rect = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    with d.begin("add_page"):
        d.add_page("P2")
    with d.begin("c1"):
        d.add_user_cloud(rect, 1.0, LINETYPE_CONTINUOUS, is_closed=True)
    d.set_current_page("P2")
    with d.begin("c2"):
        d.add_user_cloud(rect, 1.0, LINETYPE_CONTINUOUS, is_closed=True)
    assert _count_user_cloud_entities(d.doc) == 2
    with d.begin("del_all_clouds"):
        removed = d.delete_all_user_clouds_all_pages()
    assert removed == 2
    assert _count_user_cloud_entities(d.doc) == 0
