"""Tests for ATTDEF geometry copied onto INSERT ATTRIB (PDF/UI parity)."""

from __future__ import annotations

import os
import tempfile

import ezdxf
import pytest

from ezdxf.math import Vec3

from logic_cad.core.dxf.attrib_geometry_sync import (
    PDF_ATTRIB_POSITION_EQ_TOL_MM,
    apply_attdef_text_geometry_to_attrib,
    bake_paper_layout_attrib_inserts_to_wcs_for_pdf,
    dxfattribs_for_attrib_from_attdef,
    restore_paper_layout_insert_attrib_geometry,
    snapshot_paper_layout_insert_attrib_geometry,
    sync_paper_layout_insert_attrib_geometry_from_attdefs,
)
from logic_cad.core.services.pdf_export_service import export_paper_layouts_to_pdf


def test_dxfattribs_for_attrib_from_attdef_includes_alignment() -> None:
    """New ATTRIB dxfattribs should carry halign/width from ATTDEF."""

    doc = ezdxf.new("R2010", setup=["styles"])
    blk = doc.blocks.new("LB")
    attdef = blk.add_attdef(
        "LABEL0",
        (0.0, 0.7),
        "DEF",
        dxfattribs={"height": 1.7, "halign": 1, "rotation": 15.0, "width": 1.05},
    )
    attdef.dxf.align_point = (0.0, 0.7, 0.0)
    dxfattrs = dxfattribs_for_attrib_from_attdef(attdef)
    assert dxfattrs["height"] == pytest.approx(1.7)
    assert int(dxfattrs["halign"]) == 1
    assert dxfattrs["rotation"] == pytest.approx(15.0)
    assert dxfattrs["width"] == pytest.approx(1.05)


def test_apply_attdef_text_geometry_preserves_text_and_invisible() -> None:
    """Geometry copy must not replace instance text or visibility."""

    doc = ezdxf.new("R2010", setup=["styles"])
    blk = doc.blocks.new("LB2")
    attdef = blk.add_attdef(
        "LABEL0",
        (2.0, 3.0),
        "DEFAULT",
        dxfattribs={"height": 1.2, "halign": 1},
    )
    attdef.dxf.align_point = (2.0, 3.0, 0.0)
    attdef.dxf.width = 1.1

    lay_blk = doc.blocks.new("PAGE")
    ins = lay_blk.add_blockref("LB2", (100.0, 50.0))
    ins.add_attrib("LABEL0", "AL", (0.0, 0.0), dxfattribs={"height": 0.5, "halign": 0})
    a = ins.attribs[0]
    a.dxf.invisible = 1

    apply_attdef_text_geometry_to_attrib(attdef, a)

    assert str(a.dxf.text) == "AL"
    assert int(a.dxf.invisible) == 1
    assert float(a.dxf.insert.x) == pytest.approx(2.0)
    assert float(a.dxf.insert.y) == pytest.approx(3.0)
    assert int(a.dxf.halign) == 1
    assert float(a.dxf.width) == pytest.approx(1.1)
    ap = a.dxf.align_point
    assert float(ap.x) == pytest.approx(2.0) and float(ap.y) == pytest.approx(3.0)


def test_sync_paper_layout_repairs_attrib_without_align_point() -> None:
    """Layout sync copies ATTDEF alignment so ATTRIB matches block definition."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("SYM")
    attdef = sym.add_attdef(
        "LABEL0",
        (0.0, 1.0),
        "",
        dxfattribs={"height": 1.0, "halign": 1},
    )
    attdef.dxf.align_point = (0.0, 1.0, 0.0)

    lay = doc.layouts.get("Layout1")
    lay_blk = doc.blocks.get(lay.block_record_name)
    ins = lay_blk.add_blockref("SYM", (30.0, 40.0))
    ins.add_attrib("LABEL0", "XX", (0.0, 1.0), dxfattribs={"height": 1.0, "halign": 0})
    a = ins.attribs[0]
    if a.dxf.hasattr("align_point"):
        a.dxf.discard("align_point")
    assert int(a.dxf.halign) == 0

    sync_paper_layout_insert_attrib_geometry_from_attdefs(doc, "Layout1")

    assert int(a.dxf.halign) == 1
    assert a.dxf.hasattr("align_point")
    assert str(a.dxf.text) == "XX"


def test_export_pdf_with_insert_attrib_writes_file() -> None:
    """Regression: PDF export succeeds for layouts that contain INSERT + ATTRIB."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("SYM2")
    ad = sym.add_attdef("L", (0.0, 0.0), "", dxfattribs={"height": 2.5, "halign": 1})
    ad.dxf.align_point = (0.0, 0.0, 0.0)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("SYM2", (20.0, 30.0))
    ins.add_attrib("L", "t", (0.0, 0.0), dxfattribs={"height": 2.5})

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


def test_bake_pdf_skips_attrib_already_in_layout_wcs() -> None:
    """CAD-baked ATTRIB (insert already WCS) must not be transformed again."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("S_WCS")
    sym.add_attdef(tag="L", text="", insert=(2.0, 3.0, 0.0), height=1.0)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("S_WCS", (100.0, 50.0))
    ins.add_attrib("L", "t", (102.0, 53.0, 0.0))
    n = bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, "Layout1")
    assert n == 0
    assert float(ins.attribs[0].dxf.insert.x) == pytest.approx(102.0)
    assert float(ins.attribs[0].dxf.insert.y) == pytest.approx(53.0)


def test_bake_pdf_block_local_to_wcs_then_restore() -> None:
    """Block-local ATTRIB → paper WCS for matplotlib; snapshot restores live doc."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("S_LOC")
    attdef = sym.add_attdef(tag="L", text="", insert=(2.0, 3.0, 0.0), height=1.0)
    attdef.dxf.align_point = (2.0, 3.0, 0.0)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("S_LOC", (100.0, 50.0))
    a = ins.add_attrib("L", "t", (2.0, 3.0, 0.0), dxfattribs={"height": 1.0, "halign": 1})
    apply_attdef_text_geometry_to_attrib(attdef, a)
    snap = snapshot_paper_layout_insert_attrib_geometry(doc, "Layout1")
    assert len(snap) == 1
    n = bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, "Layout1")
    assert n == 1
    m = ins.matrix44()
    exp = m.transform(Vec3(2.0, 3.0, 0.0))
    assert float(a.dxf.insert.x) == pytest.approx(float(exp.x))
    assert float(a.dxf.insert.y) == pytest.approx(float(exp.y))
    restore_paper_layout_insert_attrib_geometry(doc, snap)
    assert float(a.dxf.insert.x) == pytest.approx(2.0)
    assert float(a.dxf.insert.y) == pytest.approx(3.0)


def test_bake_pdf_skips_ambiguous_attrib_position() -> None:
    """When insert matches neither block-local nor expected WCS, do not rewrite."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("S_AMB")
    sym.add_attdef(tag="L", text="", insert=(0.0, 1.0, 0.0), height=1.0)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("S_AMB", (30.0, 40.0))
    ins.add_attrib("L", "t", (11.0, 22.0, 0.0))
    n = bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, "Layout1")
    assert n == 0
    assert float(ins.attribs[0].dxf.insert.x) == pytest.approx(11.0)


def test_bake_pdf_with_rotation_and_nonuniform_scale() -> None:
    """INSERT matrix44 must map block-local ATTRIB to WCS under rotation and xy scale."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("S_ROT")
    sym.add_attdef(tag="L", text="", insert=(1.0, 0.0, 0.0), height=1.0)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("S_ROT", (10.0, 20.0))
    ins.dxf.rotation = 90.0
    ins.dxf.xscale = 2.0
    ins.dxf.yscale = 3.0
    a = ins.add_attrib("L", "x", (1.0, 0.0, 0.0))
    exp = ins.matrix44().transform(Vec3(1.0, 0.0, 0.0))
    bake_paper_layout_attrib_inserts_to_wcs_for_pdf(doc, "Layout1")
    assert float(a.dxf.insert.x) == pytest.approx(float(exp.x))
    assert float(a.dxf.insert.y) == pytest.approx(float(exp.y))


def test_export_pdf_restores_block_local_attrib_geometry() -> None:
    """Full PDF export must not leave block-local coordinates mutated on the document."""

    doc = ezdxf.new("R2010", setup=["styles"])
    sym = doc.blocks.new("S_PDF_RST")
    sym.add_attdef(tag="L", text="", insert=(3.0, 4.0, 0.0), height=2.5)
    lay = doc.layouts.get("Layout1")
    lb = doc.blocks.get(lay.block_record_name)
    ins = lb.add_blockref("S_PDF_RST", (20.0, 30.0))
    a = ins.add_attrib("L", "txt", (3.0, 4.0, 0.0), dxfattribs={"height": 2.5})
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    try:
        export_paper_layouts_to_pdf(doc, path, layout_names=["Layout1"], dpi=72)
        assert os.path.isfile(path)
        assert os.path.getsize(path) > 0
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    assert float(a.dxf.insert.x) == pytest.approx(3.0)
    assert float(a.dxf.insert.y) == pytest.approx(4.0)


def test_pdf_attrib_tol_constant_is_documented_mm() -> None:
    """Sanity: equality tolerance is a small positive mm value."""

    assert PDF_ATTRIB_POSITION_EQ_TOL_MM > 0.0
    assert PDF_ATTRIB_POSITION_EQ_TOL_MM < 1.0
