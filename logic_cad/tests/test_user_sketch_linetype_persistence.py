"""Regression tests for USER_LINE / USER_CIRCLE linetype persistence."""

from __future__ import annotations

import tempfile
from pathlib import Path

from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.model.constants import (
    LAYER_USER_CLOUD_DASHED,
    LAYER_USER_LINE_DASHED,
    LINETYPE_CONTINUOUS,
    LINETYPE_DASH,
)
from logic_cad.core.services.user_geometry_service import UserGeometryService
from logic_cad.core.undo.history import find_entity_by_uid

from logic_cad.tests.support.dxf_layouts import first_paper_layout_name


def test_user_line_linetype_persists_after_save_and_read() -> None:
    """Saved DXF keeps explicit dashed linetype for user sketch line."""
    doc = new_document()
    layout_name = first_paper_layout_name(doc)
    svc = UserGeometryService(doc)
    uid = svc.add_line(layout_name, (0.0, 0.0), (30.0, 0.0), LINETYPE_DASH)

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "user_line_persist.dxf"
        saveas(doc, path)
        loaded = readfile(path)

    entity = find_entity_by_uid(loaded, uid)
    assert entity is not None
    assert str(entity.dxf.linetype).upper() == "DASHED"


def test_saveas_restores_user_dashed_layer_linetype_definition() -> None:
    """saveas normalizes dashed user layer linetype before writing DXF."""
    doc = new_document()
    doc.layers.get(LAYER_USER_LINE_DASHED).dxf.linetype = LINETYPE_CONTINUOUS

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "user_layer_fixup.dxf"
        saveas(doc, path)

    assert str(doc.layers.get(LAYER_USER_LINE_DASHED).dxf.linetype).upper() == LINETYPE_DASH


def test_saveas_restores_user_cloud_dashed_layer_linetype_definition() -> None:
    """saveas normalizes dashed USER_CLOUD layer linetype before writing DXF."""
    doc = new_document()
    doc.layers.get(LAYER_USER_CLOUD_DASHED).dxf.linetype = LINETYPE_CONTINUOUS

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "user_cloud_layer_fixup.dxf"
        saveas(doc, path)

    assert str(doc.layers.get(LAYER_USER_CLOUD_DASHED).dxf.linetype).upper() == LINETYPE_DASH
