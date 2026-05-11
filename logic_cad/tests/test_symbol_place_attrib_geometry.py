"""INSERT child ATTRIB geometry matches ATTDEF immediately after SymbolService placement."""

from __future__ import annotations

import pytest

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import LAYER_SYMBOL
from logic_cad.core.services.block_edit_helpers import add_attdef_to_block


def _sym_attdef(doc, block_name: str):
    blk = doc.blocks.get(block_name)
    for e in blk:
        if str(e.dxftype()) == "ATTDEF" and str(e.dxf.tag).upper() == "SYM":
            return e
    raise AssertionError("SYM ATTDEF missing")


def _label_attdef(doc, block_name: str, label: str):
    u = str(label).upper()
    blk = doc.blocks.get(block_name)
    for e in blk:
        if str(e.dxftype()) == "ATTDEF" and str(e.dxf.tag).upper() == u:
            return e
    raise AssertionError(f"{label} ATTDEF missing")


def test_place_symbol_copies_attrib_align_point_after_add_auto_attribs() -> None:
    """CENTERED SYM ATTDEF: child ATTRIB must carry ``align_point`` after ``place_symbol``.

    Mirrors failure mode where ``add_auto_attribs`` leaves ``align_point`` unset while
    ``halign=1``, confusing host CAD layouts (DISC_FIELD / test99 investigations).
    """

    diag = LogicDiagram.new()
    name = "_TEST_SYM_H1_ALIGN_CK"
    blk = diag.doc.blocks.new(name)
    blk.add_point((0.0, 0.0, 0.0), dxfattribs={"layer": LAYER_SYMBOL})
    add_attdef_to_block(blk, "SYM", (0.0, 0.7), "", height_mm=2.5)
    for e in blk:
        if str(e.dxftype()) == "ATTDEF" and str(e.dxf.tag).upper() == "SYM":
            e.dxf.halign = 1

    attdef_sym = _sym_attdef(diag.doc, name)

    uid = diag.place_symbol(name, (50.0, 80.0), ref="LBL_1")
    ins = diag.symbols.insert_by_uid(diag.current_layout_name, uid)
    assert ins is not None
    sym = next((a for a in ins.attribs if str(a.dxf.tag).upper() == "SYM"), None)
    assert sym is not None
    ap = sym.dxf.align_point
    assert ap is not None, "SYM ATTRIB.align_point missing after placement sync"
    assert float(ap.x) == pytest.approx(float(attdef_sym.dxf.align_point.x))
    assert float(ap.y) == pytest.approx(float(attdef_sym.dxf.align_point.y))
    assert int(getattr(sym.dxf, "halign", 0) or 0) == 1


def test_place_symbol_no_attdef_skips_children() -> None:
    """Geometry-only block (no ATTDEF): INSERT has no child ATTRIBs."""

    diag = LogicDiagram.new()
    name = "_TEST_SYMLESS_POINT"
    blk = diag.doc.blocks.new(name)
    blk.add_point((0.5, -0.3, 0.0), dxfattribs={"layer": LAYER_SYMBOL})
    uid = diag.place_symbol(name, (10.0, 20.0), ref="-")
    ins = diag.symbols.insert_by_uid(diag.current_layout_name, uid)
    assert ins is not None
    assert list(ins.attribs) == []


def test_place_symbol_dual_label_no_sym_centers_aligned_like_disc_field() -> None:
    """Blocks with LABEL ATTDEF but no SYM (DISC_FIELD style) get synced child ATTRIBs."""

    diag = LogicDiagram.new()
    name = "_TEST_TWO_LABEL_CENTER"
    blk = diag.doc.blocks.new(name)
    blk.add_point((0.0, 0.0, 0.0), dxfattribs={"layer": LAYER_SYMBOL})
    add_attdef_to_block(blk, "LABEL0", (0.0, 0.7), "la0", height_mm=2.5)
    add_attdef_to_block(blk, "LABEL1", (0.0, -2.3), "la1", height_mm=2.5)
    for e in blk:
        if str(e.dxftype()) == "ATTDEF" and str(e.dxf.tag).upper().startswith("LABEL"):
            e.dxf.halign = 1

    uid = diag.place_symbol(name, (60.0, 110.0), ref="-")
    ins = diag.symbols.insert_by_uid(diag.current_layout_name, uid)
    assert ins is not None
    assert len(ins.attribs) >= 2
    attdef0 = _label_attdef(diag.doc, name, "LABEL0")
    attdef1 = _label_attdef(diag.doc, name, "LABEL1")
    by_tag = {str(a.dxf.tag).upper(): a for a in ins.attribs}
    for tag, ad in (("LABEL0", attdef0), ("LABEL1", attdef1)):
        a = by_tag[tag]
        ap = a.dxf.align_point
        assert ap is not None, f"{tag} missing align_point"
        assert float(ap.x) == pytest.approx(float(ad.dxf.align_point.x))
        assert float(ap.y) == pytest.approx(float(ad.dxf.align_point.y))
        assert int(getattr(a.dxf, "halign", 0) or 0) == 1
