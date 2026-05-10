"""TOC contents area bbox helpers and grid counts."""

from unittest.mock import MagicMock

import ezdxf
import pytest

from logic_cad.core.model.constants import (
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
    CONTENTS_CELL_COL_GAP_MM,
    CONTENTS_CELL_HEIGHT_MM,
    CONTENTS_CELL_ROW_GAP_MM,
    CONTENTS_CELL_WIDTH_MM,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    LAYER_CONTENTS_AREA,
    TOC_LAYOUT_NAME,
)
from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.services.layout_service import LayoutService, ensure_frame_template_blocks
from logic_cad.core.services.toc_frame_service import (
    _contents_frame_bbox_size_mm,
    _default_contents_bbox,
    _regenerate_toc_mtext_fallback,
    _toc_cell_metrics_from_contents_frame,
    regenerate_toc,
)
from logic_cad.core.pages.toc_contents_layout import contents_area_bbox_mm, toc_grid_cols_and_data_rows
from logic_cad.core.model.xdata import get_type, get_uid


def test_toc_grid_cols_and_rows() -> None:
    cols, rows_d = toc_grid_cols_and_data_rows(0.0, 0.0, 120.0, 48.0, 60.0, 8.0, 8.0, 0.0, 0.0)
    assert cols == 2
    assert rows_d == 5


def test_toc_grid_zero_height_data_rows() -> None:
    cols, rows_d = toc_grid_cols_and_data_rows(0.0, 0.0, 100.0, 10.0, 60.0, 8.0, 8.0, 0.0, 0.0)
    assert cols == 1
    assert rows_d == 0


def test_contents_area_bbox_from_block() -> None:
    doc = ezdxf.new("R2010", setup=False)
    doc.layers.add(LAYER_CONTENTS_AREA)
    blk = doc.blocks.new("TEST_BLK")
    blk.add_lwpolyline(
        [(10.0, 50.0), (110.0, 50.0), (110.0, 10.0), (10.0, 10.0)],
        close=True,
        dxfattribs={"layer": LAYER_CONTENTS_AREA},
    )
    bb = contents_area_bbox_mm(blk)
    assert bb == (10.0, 10.0, 110.0, 50.0)


def test_non_toc_layout_has_no_ld_contents_area_guide() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("SheetA")
    blk = doc.blocks.get(doc.layouts.get("SheetA").block_record_name)
    assert not any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk)


def test_contents_frame_bbox_size_matches_template_cell() -> None:
    doc = new_document()
    ensure_frame_template_blocks(doc)
    row_wh = _contents_frame_bbox_size_mm(doc, BLOCK_CONTENTS_ROW)
    hdr_wh = _contents_frame_bbox_size_mm(doc, BLOCK_CONTENTS_HEADER)
    assert row_wh is not None and hdr_wh is not None
    rw, rh = row_wh
    hw, hh = hdr_wh
    assert abs(rw - CONTENTS_CELL_WIDTH_MM) < 1e-3
    assert abs(rh - CONTENTS_CELL_HEIGHT_MM) < 1e-3
    assert abs(hw - CONTENTS_CELL_WIDTH_MM) < 1e-3
    assert abs(hh - CONTENTS_CELL_HEIGHT_MM) < 1e-3


def test_regenerate_toc_inserts_header_and_rows() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("DocPage")
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    regenerate_toc(doc)
    blk = doc.blocks.get(doc.layouts.get(TOC_LAYOUT_NAME).block_record_name)
    types = [get_type(e) for e in blk if e.dxftype() == "INSERT"]
    assert ENTITY_TYPE_TOC_HEADER in types
    assert ENTITY_TYPE_TOC_ROW in types


def test_regenerate_toc_row_count_matches_grid_capacity() -> None:
    """Every data cell in the contents area gets a CONTENTS_ROW (padded empties)."""
    doc = new_document()
    ls = LayoutService(doc)
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    regenerate_toc(doc)
    blk = doc.blocks.get(doc.layouts.get(TOC_LAYOUT_NAME).block_record_name)
    cell_w, cell_h, hdr_h = _toc_cell_metrics_from_contents_frame(doc)
    bb = contents_area_bbox_mm(blk) or _default_contents_bbox()
    cols, rows_d = toc_grid_cols_and_data_rows(
        bb[0],
        bb[1],
        bb[2],
        bb[3],
        cell_w,
        cell_h,
        hdr_h,
        CONTENTS_CELL_COL_GAP_MM,
        CONTENTS_CELL_ROW_GAP_MM,
    )
    cap = cols * rows_d
    assert cap >= 1
    n_row_ins = sum(1 for e in blk if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_TOC_ROW)
    assert n_row_ins == cap


def test_import_frame_template_skips_ld_contents_area_on_paper() -> None:
    """Template modelspace guide is not copied into paper blocks."""
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("T1")
    blk = doc.blocks.get(doc.layouts.get("T1").block_record_name)
    assert not any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk)


def test_toc_layout_has_no_top_level_ld_contents_area_after_template_import() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    blk = doc.blocks.get(doc.layouts.get(TOC_LAYOUT_NAME).block_record_name)
    assert not any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk)


def test_saveas_and_readfile_strip_ld_contents_area_from_paper(tmp_path) -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("Q1")
    blk = doc.blocks.get(doc.layouts.get("Q1").block_record_name)
    blk.add_lwpolyline(
        [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)],
        close=True,
        dxfattribs={"layer": LAYER_CONTENTS_AREA},
    )
    assert any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk)
    p = tmp_path / "strip_area.dxf"
    saveas(doc, p)
    assert not any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk)
    doc2 = readfile(p)
    blk2 = doc2.blocks.get(doc2.layouts.get("Q1").block_record_name)
    assert not any(str(e.dxf.layer) == LAYER_CONTENTS_AREA for e in blk2)


def test_regenerate_toc_debug_logs_when_ld_contents_area_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paper TOC block has no LD_CONTENTS_AREA polyline; log default bbox fallback."""
    mock_log = MagicMock()
    monkeypatch.setattr(
        "logic_cad.core.services.toc_frame_service.logic_cad_log",
        mock_log,
    )
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("DocPage")
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    regenerate_toc(doc)
    toc_msgs = [c[0][1] for c in mock_log.call_args_list if c[0][0] == "toc"]
    assert any("LD_CONTENTS_AREA" in m for m in toc_msgs)


def test_toc_cell_metrics_debug_logs_when_template_geometry_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No LD_CONTENTS_FRAME extents for CONTENTS_* blocks; log cell constant fallback."""
    mock_log = MagicMock()
    monkeypatch.setattr(
        "logic_cad.core.services.toc_frame_service.logic_cad_log",
        mock_log,
    )
    doc = new_document()
    monkeypatch.setattr(
        "logic_cad.core.services.toc_frame_service._contents_frame_bbox_size_mm",
        lambda *_a, **_k: None,
    )
    _toc_cell_metrics_from_contents_frame(doc)
    toc_msgs = [c[0][1] for c in mock_log.call_args_list if c[0][0] == "toc"]
    assert any("CONTENTS_CELL" in m for m in toc_msgs)


def test_regenerate_toc_mtext_fallback_emits_debug_log(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_log = MagicMock()
    monkeypatch.setattr(
        "logic_cad.core.services.toc_frame_service.logic_cad_log",
        mock_log,
    )
    doc = new_document()
    ls = LayoutService(doc)
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    ls.add_page("OnlyPage")
    _regenerate_toc_mtext_fallback(doc, ls, TOC_LAYOUT_NAME, ["OnlyPage"])
    mock_log.assert_called_once()
    assert mock_log.call_args[0][0] == "toc"
    assert "MTEXT" in mock_log.call_args[0][1]


def test_delete_by_uid_does_not_remove_toc_row_on_toc_sheet() -> None:
    doc = new_document()
    ls = LayoutService(doc)
    ls.add_page("Z9")
    doc.layouts.new(TOC_LAYOUT_NAME)
    ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    regenerate_toc(doc)
    blk = doc.blocks.get(doc.layouts.get(TOC_LAYOUT_NAME).block_record_name)
    uid = next(
        (get_uid(e) for e in blk if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_TOC_ROW),
        None,
    )
    assert uid
    before = sum(1 for e in blk if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_TOC_ROW)
    d = LogicDiagram(doc, TOC_LAYOUT_NAME)
    d.delete_by_uid(uid)
    after = sum(1 for e in blk if e.dxftype() == "INSERT" and get_type(e) == ENTITY_TYPE_TOC_ROW)
    assert after == before
