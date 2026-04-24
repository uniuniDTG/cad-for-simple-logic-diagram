"""Tests for document-level LD_DOC XDATA (``document_meta`` module)."""

from __future__ import annotations

import ezdxf

from logic_cad import __version__ as PKG_VERSION
from logic_cad.core.dxf.dxf_repository import new_document, readfile, saveas
from logic_cad.core.model.constants import LAYER_DOC_META
from logic_cad.core.model.document_meta import (
    DOC_FORMAT_VERSION,
    PREFERRED_FONT_FAMILY_KEY,
    apply_document_meta_stamp,
    find_document_meta_entity,
    read_document_meta,
    read_document_meta_dict,
    read_project_preferred_font_family,
    set_project_preferred_font_family,
)


def test_new_document_has_document_meta() -> None:
    doc = new_document()
    meta = read_document_meta(doc)
    assert meta is not None
    assert meta.creator == "Logic CAD"
    assert meta.app_version == PKG_VERSION
    assert meta.doc_format == DOC_FORMAT_VERSION
    assert meta.dxf_profile == "R2010"


def test_saveas_roundtrip_preserves_document_meta(tmp_path) -> None:
    doc = new_document()
    path = tmp_path / "round.dxf"
    saveas(doc, path)
    doc2 = readfile(path)
    meta = read_document_meta(doc2)
    assert meta is not None
    assert meta.creator == "Logic CAD"
    assert meta.app_version == PKG_VERSION
    assert meta.doc_format == DOC_FORMAT_VERSION
    assert meta.dxf_profile == "R2010"


def test_minimal_dxf_without_anchor_returns_none(tmp_path) -> None:
    doc = ezdxf.new("R2010", setup=False)
    path = tmp_path / "bare.dxf"
    doc.saveas(str(path))
    doc2 = readfile(path)
    assert read_document_meta(doc2) is None


def test_apply_stamp_creates_layer_and_point() -> None:
    doc = ezdxf.new("R2010", setup=False)
    assert LAYER_DOC_META not in doc.layers
    apply_document_meta_stamp(doc)
    assert LAYER_DOC_META in doc.layers
    meta = read_document_meta(doc)
    assert meta is not None
    assert meta.doc_format == DOC_FORMAT_VERSION


def test_project_preferred_font_roundtrip_and_stamp_preserves() -> None:
    doc = new_document()
    set_project_preferred_font_family(doc, "Yu Gothic UI")
    assert read_project_preferred_font_family(doc) == "Yu Gothic UI"
    apply_document_meta_stamp(doc)
    assert read_project_preferred_font_family(doc) == "Yu Gothic UI"
    ent = find_document_meta_entity(doc)
    assert ent is not None
    d = read_document_meta_dict(ent)
    assert d.get(PREFERRED_FONT_FAMILY_KEY) == "Yu Gothic UI"


def test_project_preferred_font_clear() -> None:
    doc = new_document()
    set_project_preferred_font_family(doc, "Meiryo")
    assert read_project_preferred_font_family(doc) == "Meiryo"
    set_project_preferred_font_family(doc, None)
    assert read_project_preferred_font_family(doc) is None
