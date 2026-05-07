"""symbol_library.dxf import and block-name iteration (ezdxf version differences)."""

from pathlib import Path

import ezdxf
import pytest

from logic_cad.core.model.constants import BLOCK_CHECKPOINT
from logic_cad.core.dxf.dxf_repository import new_document
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory
from logic_cad.core.services.layout_service import (
    _iter_block_definition_names,
    import_symbol_library,
    list_palette_block_names,
    reload_symbol_library,
)
from logic_cad.core.services.symbol_service import SymbolService


def test_iter_block_definition_names_returns_strings_and_user_blocks():
    doc = new_document()
    blk = doc.blocks.new("USER_BLOCK_A")
    blk.add_line((0, 0), (1, 0), dxfattribs={"layer": "0"})
    names = _iter_block_definition_names(doc.blocks)
    assert all(isinstance(n, str) for n in names)
    assert "USER_BLOCK_A" in names
    # anonymous layout blocks exist with * prefix
    assert any(n.startswith("*") for n in names)


def test_reload_symbol_library_replaces_existing_block_geometry(tmp_path: Path) -> None:
    """Existing block definitions are updated in place (no NAME0 duplicate)."""
    lib_path = tmp_path / "lib.dxf"

    def write_lib(end_x: float) -> None:
        src = ezdxf.new("R2010", setup=True)
        blk = src.blocks.new("RELOAD_ME")
        blk.add_line((0, 0), (end_x, 0), dxfattribs={"layer": "LD_SYMBOL"})
        src.saveas(str(lib_path))

    write_lib(1.0)
    doc = new_document()
    import_symbol_library(doc, path=lib_path)
    line0 = next(e for e in doc.blocks.get("RELOAD_ME") if e.dxftype() == "LINE")
    assert float(line0.dxf.end[0]) == 1.0

    write_lib(5.0)
    reload_symbol_library(doc, path=lib_path)
    line1 = next(e for e in doc.blocks.get("RELOAD_ME") if e.dxftype() == "LINE")
    assert float(line1.dxf.end[0]) == 5.0
    assert "RELOAD_ME0" not in doc.blocks


def test_reload_symbol_library_merges_new_block_names(tmp_path: Path) -> None:
    """Blocks that appear only in an updated library file are added on reload."""
    lib_path = tmp_path / "lib.dxf"
    src = ezdxf.new("R2010", setup=True)
    blk = src.blocks.new("ONLY_OLD")
    blk.add_circle((0, 0), 1.0, dxfattribs={"layer": "LD_SYMBOL"})
    src.saveas(str(lib_path))

    doc = new_document()
    import_symbol_library(doc, path=lib_path)
    assert "BRAND_NEW" not in doc.blocks

    src2 = ezdxf.readfile(str(lib_path))
    nb = src2.blocks.new("BRAND_NEW")
    nb.add_line((0, 0), (2, 0), dxfattribs={"layer": "LD_SYMBOL"})
    src2.saveas(str(lib_path))

    reload_symbol_library(doc, path=lib_path)
    assert "BRAND_NEW" in doc.blocks
    assert any(e.dxftype() == "LINE" for e in doc.blocks.get("BRAND_NEW"))


def test_import_symbol_library_merges_blocks_from_file(tmp_path: Path) -> None:
    src_path = tmp_path / "mini_lib.dxf"
    src = ezdxf.new("R2010", setup=True)
    blk = src.blocks.new("IMPORTED_COIL")
    blk.add_line((0, 0), (2, 0), dxfattribs={"layer": "LD_SYMBOL"})
    src.saveas(str(src_path))

    doc = new_document()
    assert "IMPORTED_COIL" not in doc.blocks

    import_symbol_library(doc, path=src_path)

    assert "IMPORTED_COIL" in doc.blocks
    b = doc.blocks.get("IMPORTED_COIL")
    assert b is not None
    assert any(e.dxftype() == "LINE" for e in b)


def test_list_palette_block_names_excludes_system_blocks() -> None:
    doc = new_document()
    import_symbol_library(doc)
    doc.blocks.new("CONTENTS_HEADER")
    doc.blocks.new("CONTENTS_ROW")
    names = set(list_palette_block_names(doc))
    for b in ("CONTENTS_HEADER", "CONTENTS_ROW", "PAGE_FROM", "PAGE_TO"):
        assert b not in names
    assert BLOCK_CHECKPOINT not in names


def test_import_symbol_library_missing_file_ensures_system_blocks_only(tmp_path: Path) -> None:
    doc = new_document()
    missing = tmp_path / "no_such_library.dxf"
    assert not missing.is_file()
    import_symbol_library(doc, path=missing)
    assert "NOT" not in doc.blocks
    assert BLOCK_CHECKPOINT in doc.blocks
    assert "PAGE_TO" in doc.blocks
    assert "PAGE_FROM" in doc.blocks


def test_large_library_block_gets_uniform_scale_on_place() -> None:
    """Large library blocks should use uniform XY scale; scale may be < 1 when downsized for layout."""
    doc = new_document()
    import_symbol_library(doc)
    flipflop_name = "FLIPFLOP(SR)"
    if flipflop_name not in doc.blocks:
        pytest.skip("symbol_library.dxf has no FLIPFLOP block")
    names = [L.name for L in doc.layouts if not L.is_modelspace]
    assert names
    first = names[0]
    ss = SymbolService(doc, DynamicGateFactory())
    uid = ss.place_symbol(first, flipflop_name, (30.0, 40.0), "U1", "SYMBOL")
    ins = ss.insert_by_uid(first, uid)
    assert ins is not None
    xs, ys = float(ins.dxf.xscale), float(ins.dxf.yscale)
    assert xs > 0 and ys > 0
    assert abs(xs - ys) < 1e-6
    assert xs <= 1.0
