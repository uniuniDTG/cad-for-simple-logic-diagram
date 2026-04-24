"""Drawing declares millimeter insertion units."""

from __future__ import annotations

import tempfile
from pathlib import Path

from logic_cad.core.dxf.dxf_repository import ensure_drawing_units_mm, new_document, readfile, saveas


def test_new_document_insunits_mm() -> None:
    doc = new_document()
    assert doc.units == 4


def test_readfile_normalizes_insunits_mm() -> None:
    doc = new_document()
    doc.header["$INSUNITS"] = 6
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.dxf"
        saveas(doc, p)
        doc2 = readfile(p)
        assert doc2.units == 4


def test_ensure_drawing_units_mm_helper() -> None:
    doc = new_document()
    doc.header["$INSUNITS"] = 1
    ensure_drawing_units_mm(doc)
    assert doc.units == 4
