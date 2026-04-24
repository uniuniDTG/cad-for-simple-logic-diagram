"""Tests for user sketch linetype behavior in UserGeometryService."""

from __future__ import annotations

from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.model.constants import (
    LAYER_USER_CIRCLE_CENTER,
    LAYER_USER_CLOUD_CENTER,
    LAYER_USER_LINE_CENTER,
    LAYER_USER_LINE_DASHED,
    LINETYPE_CONTINUOUS,
    LINETYPE_DASH,
)
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.undo.history import find_entity_by_uid

from logic_cad.tests.support.dxf_layouts import first_paper_layout_name


def test_add_line_sets_explicit_dashed_linetype() -> None:
    """add_line stores dashed linetype explicitly on the entity."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    uid = svc.add_line(layout_name, (0.0, 0.0), (20.0, 0.0), LINETYPE_DASH)
    entity = find_entity_by_uid(doc, uid)

    assert entity is not None
    assert str(entity.dxf.layer) == LAYER_USER_LINE_DASHED
    assert str(entity.dxf.linetype).upper() == "DASHED"


def test_set_user_line_or_circle_linetype_updates_layer_and_entity_linetype() -> None:
    """set_user_line_or_circle_linetype updates both layer and explicit linetype."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    line_uid = svc.add_line(layout_name, (0.0, 0.0), (10.0, 0.0), LINETYPE_CONTINUOUS)
    circle_uid = svc.add_circle(layout_name, (5.0, 5.0), 2.0, LINETYPE_CONTINUOUS)

    assert svc.set_user_line_or_circle_linetype(layout_name, line_uid, "CENTER") is True
    assert svc.set_user_line_or_circle_linetype(layout_name, circle_uid, "CENTER") is True

    line_entity = find_entity_by_uid(doc, line_uid)
    circle_entity = find_entity_by_uid(doc, circle_uid)

    assert line_entity is not None
    assert circle_entity is not None
    assert str(line_entity.dxf.layer) == LAYER_USER_LINE_CENTER
    assert str(line_entity.dxf.linetype).upper() == "CENTER"
    assert str(circle_entity.dxf.layer) == LAYER_USER_CIRCLE_CENTER
    assert str(circle_entity.dxf.linetype).upper() == "CENTER"


def test_set_user_cloud_linetype_updates_layer_and_entity_linetype() -> None:
    """USER_CLOUD also follows the USER layer-by-linetype mapping."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)

    cloud_uid = svc.add_cloud(
        layout_name,
        [(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)],
        segment_length=1.0,
        linetype=LINETYPE_CONTINUOUS,
        is_closed=True,
    )
    assert svc.set_user_line_or_circle_linetype(layout_name, cloud_uid, "CENTER") is True

    cloud_entity = find_entity_by_uid(doc, cloud_uid)
    assert cloud_entity is not None
    assert str(cloud_entity.dxf.layer) == LAYER_USER_CLOUD_CENTER
    assert str(cloud_entity.dxf.linetype).upper() == "CENTER"
