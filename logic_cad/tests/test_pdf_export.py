"""Smoke and unit tests for PDF export."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import ezdxf
import pytest

from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_WIDTH_MM,
    LAYER_CONTENTS_AREA,
    LAYER_DOC_META,
    LAYER_PORT,
    LAYER_USER_LINE_DASHED,
    LAYER_VPORT,
)
from logic_cad.core.logic_diagram import LogicDiagram
from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
from logic_cad.core.undo.history import find_entity_by_uid

from logic_cad.core.services.pdf_export_service import (
    PdfExportCancelled,
    PdfExportOptions,
    _paper_size_inches_from_layout,
    configuration_for_pdf_export,
    export_paper_layouts_to_pdf,
    pdf_export_entity_filter,
)


def _mock_graphic(layer: str) -> MagicMock:
    ent = MagicMock()
    ent.dxf.layer = layer
    return ent


def test_pdf_export_entity_filter_excludes_ld_port() -> None:
    assert pdf_export_entity_filter(_mock_graphic(LAYER_PORT)) is False
    assert pdf_export_entity_filter(_mock_graphic("LD_PORT_IN0_LOGIC")) is False
    assert pdf_export_entity_filter(_mock_graphic("LD_PORT_OUT0_LOGIC")) is False


def test_pdf_export_entity_filter_keeps_other_layers() -> None:
    assert pdf_export_entity_filter(_mock_graphic("LD_SYMBOL")) is True
    assert pdf_export_entity_filter(_mock_graphic("LD_TEXT")) is True
    assert pdf_export_entity_filter(_mock_graphic("0")) is True


def test_pdf_export_entity_filter_excludes_ld_checkpoint_decor_layer() -> None:
    assert pdf_export_entity_filter(_mock_graphic("LD_CHECKPOINT")) is False
    assert pdf_export_entity_filter(_mock_graphic("LD_CHECKPOINT_OUTLINE")) is False


def test_pdf_export_entity_filter_excludes_auxiliary_guide_layers() -> None:
    assert pdf_export_entity_filter(_mock_graphic(LAYER_CONTENTS_AREA)) is False
    assert pdf_export_entity_filter(_mock_graphic(LAYER_DOC_META)) is False
    assert pdf_export_entity_filter(_mock_graphic(LAYER_VPORT)) is False


def test_paper_size_inches_from_layout_a4_landscape() -> None:
    """New document paper layout stores A4 landscape mm; helper returns matching inches."""
    diagram = LogicDiagram.new()
    layout_name = diagram.list_pages()[0]
    layout = diagram.doc.layouts.get(layout_name)
    w_in, h_in = _paper_size_inches_from_layout(layout)
    assert w_in == pytest.approx(A4_LANDSCAPE_WIDTH_MM / 25.4)
    assert h_in == pytest.approx(A4_LANDSCAPE_HEIGHT_MM / 25.4)


def test_paper_size_inches_from_layout_fallback_when_paper_zero() -> None:
    """Invalid paper dimensions fall back to A4 landscape constants."""
    diagram = LogicDiagram.new()
    layout_name = diagram.list_pages()[0]
    layout = diagram.doc.layouts.get(layout_name)
    layout.dxf_layout.dxf.paper_width = 0
    layout.dxf_layout.dxf.paper_height = 0
    w_in, h_in = _paper_size_inches_from_layout(layout)
    assert w_in == pytest.approx(A4_LANDSCAPE_WIDTH_MM / 25.4)
    assert h_in == pytest.approx(A4_LANDSCAPE_HEIGHT_MM / 25.4)


def test_configuration_for_pdf_export_monochrome() -> None:
    base = Configuration()
    out = configuration_for_pdf_export(base, PdfExportOptions(monochrome=True))
    assert out.color_policy == ColorPolicy.BLACK
    assert out.background_policy == BackgroundPolicy.WHITE
    out2 = configuration_for_pdf_export(base, PdfExportOptions(monochrome=False))
    assert out2.color_policy == base.color_policy
    assert out2.background_policy == base.background_policy


def test_export_new_document_pdf_nonzero_size() -> None:
    d = LogicDiagram.new()
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(
            d.doc,
            path,
            layout_names=d.list_pages(),
            dpi=72,
        )
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_export_new_document_pdf_monochrome_nonzero_size() -> None:
    d = LogicDiagram.new()
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(
            d.doc,
            path,
            layout_names=d.list_pages(),
            dpi=72,
            export_options=PdfExportOptions(monochrome=True),
        )
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_export_pdf_progress_callback_once_per_page() -> None:
    d = LogicDiagram.new()
    pages = d.list_pages()
    calls: list[tuple[int, int]] = []
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(
            d.doc,
            path,
            layout_names=pages,
            dpi=72,
            progress_callback=lambda done, total: calls.append((done, total)),
        )
        assert len(calls) == len(pages)
        assert calls[-1] == (len(pages), len(pages))
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_export_pdf_insert_with_ld_port_point_writes_file() -> None:
    """Regression: port POINT lives inside block ref; filter must apply to virtual_entities."""
    doc = ezdxf.new("R2010", setup=["styles"])
    doc.layers.add("LD_PORT_IN0_LOGIC")
    doc.layers.add("LD_SYMBOL")
    blk = doc.blocks.new("T_SYM_WITH_PORT")
    blk.add_point((0, 0), dxfattribs={"layer": "LD_PORT_IN0_LOGIC"})
    blk.add_line((0, 0), (10, 0), dxfattribs={"layer": "LD_SYMBOL"})
    layout = doc.layouts.get("Layout1")
    layout.add_blockref("T_SYM_WITH_PORT", (50.0, 50.0))
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(
            doc,
            path,
            layout_names=["Layout1"],
            dpi=72,
        )
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def test_export_pdf_cancel_before_first_page_removes_file() -> None:
    d = LogicDiagram.new()
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    assert os.path.isfile(path)

    with pytest.raises(PdfExportCancelled):
        export_paper_layouts_to_pdf(
            d.doc,
            path,
            layout_names=d.list_pages(),
            dpi=72,
            is_cancelled=lambda: True,
        )
    assert not os.path.isfile(path)


def test_export_pdf_keeps_user_line_linetype_and_layer() -> None:
    """PDF export keeps explicit user line linetype/layer metadata unchanged."""
    d = LogicDiagram.new()
    page = d.list_pages()[0]
    uid = d.user_geom.add_line(page, (5.0, 5.0), (30.0, 5.0), "DASHED")
    before = find_entity_by_uid(d.doc, uid)
    assert before is not None
    assert str(before.dxf.layer) == LAYER_USER_LINE_DASHED
    assert str(before.dxf.linetype).upper() == "DASHED"

    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(
            d.doc,
            path,
            layout_names=d.list_pages(),
            dpi=72,
        )
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    after = find_entity_by_uid(d.doc, uid)
    assert after is not None
    assert str(after.dxf.layer) == LAYER_USER_LINE_DASHED
    assert str(after.dxf.linetype).upper() == "DASHED"
