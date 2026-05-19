"""Tests for ``LOGIC_CAD_FONT`` TEXTSTYLE and save-time host-CAD font reassignment."""

from __future__ import annotations

from pathlib import Path

import ezdxf

from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.model.constants import TEXT_STYLE_LOGIC_CAD_FONT
from logic_cad.core.model.document_meta import set_project_preferred_font_family
from logic_cad.core.text.layout_resolver import preferred_ui_font_family


def test_new_document_defines_logic_cad_font_style() -> None:
    """Fresh drawings must ship the named Japanese-capable TEXTSTYLE."""

    doc = new_document()
    assert TEXT_STYLE_LOGIC_CAD_FONT in doc.styles
    ts = doc.styles.get(TEXT_STYLE_LOGIC_CAD_FONT)
    assert "msgothic" in str(ts.dxf.font).lower()


def test_preferred_ui_font_family_maps_logic_cad_style_to_ms_gothic() -> None:
    """Without a document, treat ``LOGIC_CAD_FONT`` like MS Gothic for UI fallback."""

    assert preferred_ui_font_family(TEXT_STYLE_LOGIC_CAD_FONT) == "MS Gothic"


def test_saveas_reassigns_standard_text_to_logic_cad_font(tmp_path: Path) -> None:
    """Pre-save hook must retarget default-styled TEXT entities for BricsCAD."""

    doc = new_document()
    blk = doc.blocks.new("B1")
    ent = blk.add_text("x", height=2.5, dxfattribs={"layer": "0"})
    assert str(ent.dxf.style).strip().upper() in {"", "STANDARD"}
    saveas(doc, tmp_path / "out.dxf")
    assert str(ent.dxf.style) == TEXT_STYLE_LOGIC_CAD_FONT


def test_saveas_preserves_custom_text_style(tmp_path: Path) -> None:
    """Explicit TEXTSTYLE names from other CAD must survive save normalization."""

    doc = new_document()
    doc.styles.add("CustomCAD", font="arial.ttf")
    msp = doc.modelspace()
    ent = msp.add_text("z", height=2.0, dxfattribs={"style": "CustomCAD", "layer": "0"})
    saveas(doc, tmp_path / "custom.dxf")
    assert str(ent.dxf.style) == "CustomCAD"


def test_project_preferred_font_updates_logic_cad_textstyle_file() -> None:
    """Changing LD_DOC preferred font should refresh the single DXF font slot."""

    doc = new_document()
    set_project_preferred_font_family(doc, "Meiryo")
    ts = doc.styles.get(TEXT_STYLE_LOGIC_CAD_FONT)
    assert "meiryo" in str(ts.dxf.font).lower()


def test_readfile_defines_logic_cad_font_on_minimal_foreign_dxf(tmp_path: Path) -> None:
    """Loaded drawings without our style still gain ``LOGIC_CAD_FONT`` for merge/save paths."""

    bare = ezdxf.new("R2010", setup=["styles"])
    p = tmp_path / "bare.dxf"
    bare.saveas(str(p))
    doc = readfile(p)
    assert TEXT_STYLE_LOGIC_CAD_FONT in doc.styles
