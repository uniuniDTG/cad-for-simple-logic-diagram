"""Regression tests for UserCloudItem QPainterPath (canvas tessellation)."""

from __future__ import annotations

import math

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.model.constants import LINETYPE_CONTINUOUS
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.tests.support.dxf_layouts import first_paper_layout_name
from logic_cad.ui.bulge_path import dxf_to_scene
from logic_cad.ui.items.user_geometry_items import UserCloudItem


def _path_diagonal_mm(item: UserCloudItem) -> float:
    """Length of the diagonal of the path's axis-aligned bounding rect (scene mm)."""
    r = item.path().boundingRect()
    return float(math.hypot(r.width(), r.height()))


def _endpoint_distance_to_dxf(item: UserCloudItem, x: float, y: float) -> float:
    """Return distance between current path endpoint and expected DXF point.

    Args:
        item: Cloud item whose path endpoint is validated.
        x: Expected endpoint X in DXF mm.
        y: Expected endpoint Y in DXF mm.

    Returns:
        Distance in scene units (mm).
    """
    expected = dxf_to_scene(float(x), float(y))
    current = item.path().currentPosition()
    return float(math.hypot(current.x() - expected.x(), current.y() - expected.y()))


def test_closed_cloud_path_bounding_invariant_across_quadrant_offsets() -> None:
    """Same closed cloud translated to each quadrant keeps similar path extent (no runaway spiral).

    Pure translation must not change the size of the tessellated path's bounding box.
    """
    base_rect = [(0.0, 0.0), (12.0, 0.0), (12.0, 6.0), (0.0, 6.0)]
    offsets = [
        (0.0, 0.0),
        (150.0, 150.0),
        (-150.0, 150.0),
        (-150.0, -150.0),
        (150.0, -150.0),
    ]
    diagonals: list[float] = []
    for ox, oy in offsets:
        doc = new_document()
        layout_name = first_paper_layout_name(doc)
        svc = UserGeometryService(doc)
        verts = [(x + ox, y + oy) for x, y in base_rect]
        uid = svc.add_cloud(
            layout_name,
            verts,
            segment_length=1.0,
            linetype=LINETYPE_CONTINUOUS,
            is_closed=True,
        )
        entity = find_entity_by_uid(doc, uid)
        assert entity is not None
        points_xyb = [
            (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
            for row in entity.get_points("xyb")
        ]
        item = UserCloudItem(uid, points_xyb, is_closed=True, linetype=LINETYPE_CONTINUOUS)
        d = _path_diagonal_mm(item)
        diagonals.append(d)
        assert d < 400.0, f"path diagonal unexpectedly large at offset ({ox}, {oy}): {d}"

    ref = diagonals[0]
    for i, d in enumerate(diagonals[1:], start=1):
        assert math.isclose(d, ref, rel_tol=0.02, abs_tol=0.5), (
            f"translation should not change bbox size: ref={ref} got={d} at index {i}, all={diagonals}"
        )


def test_open_cloud_path_endpoint_and_bounding_stable_across_offsets() -> None:
    """Open cloud keeps finite extent and endpoint anchored at the last DXF point.

    This guards against canvas-only runaway arcs while preserving exact chord-end
    anchoring for each tessellated bulge segment.
    """
    base_vertices = [(-20.0, -5.0), (-4.0, 8.0), (16.0, -2.0), (32.0, 12.0)]
    offsets = [
        (0.0, 0.0),
        (180.0, 160.0),
        (-180.0, 160.0),
        (-180.0, -160.0),
        (180.0, -160.0),
    ]
    diagonals: list[float] = []
    for ox, oy in offsets:
        doc = new_document()
        layout_name = first_paper_layout_name(doc)
        svc = UserGeometryService(doc)
        verts = [(x + ox, y + oy) for x, y in base_vertices]
        uid = svc.add_cloud(
            layout_name,
            verts,
            segment_length=1.2,
            linetype=LINETYPE_CONTINUOUS,
            is_closed=False,
        )
        entity = find_entity_by_uid(doc, uid)
        assert entity is not None
        points_xyb = [
            (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
            for row in entity.get_points("xyb")
        ]
        item = UserCloudItem(uid, points_xyb, is_closed=False, linetype=LINETYPE_CONTINUOUS)
        d = _path_diagonal_mm(item)
        diagonals.append(d)
        assert d < 600.0, f"open path diagonal unexpectedly large at offset ({ox}, {oy}): {d}"
        x_end, y_end, _ = points_xyb[-1]
        assert _endpoint_distance_to_dxf(item, x_end, y_end) <= 1e-6

    ref = diagonals[0]
    for i, d in enumerate(diagonals[1:], start=1):
        assert math.isclose(d, ref, rel_tol=0.02, abs_tol=0.5), (
            f"open translation should not change bbox size: ref={ref} got={d} at index {i}, all={diagonals}"
        )


def test_closed_cloud_path_closes_to_start_point() -> None:
    """Closed cloud current endpoint returns to the first DXF point."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_cloud(
        layout_name,
        [(10.0, 12.0), (28.0, 12.0), (25.0, 25.0), (7.0, 23.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    entity = find_entity_by_uid(doc, uid)
    assert entity is not None
    points_xyb = [
        (float(row[0]), float(row[1]), float(row[2]) if len(row) > 2 else 0.0)
        for row in entity.get_points("xyb")
    ]
    item = UserCloudItem(uid, points_xyb, is_closed=True, linetype=LINETYPE_CONTINUOUS)
    x0, y0, _ = points_xyb[0]
    assert _endpoint_distance_to_dxf(item, x0, y0) <= 1e-6
