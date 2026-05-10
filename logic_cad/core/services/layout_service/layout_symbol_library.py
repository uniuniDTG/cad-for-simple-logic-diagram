"""Merge and in-place refresh of symbol library block definitions."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing

from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.dxf.dxf_repository import ensure_standard_layers
from .layout_block_names import _iter_block_definition_names
from .layout_builtin_blocks import (
    ensure_checkpoint_block,
    ensure_cross_page_reference_blocks,
    ensure_wire_branch_block,
)
from .layout_paths import assets_dir
from logic_cad.core.undo.history import destroy_entity


def import_symbol_library(doc: Drawing, path: Path | None = None) -> None:
    """Merge blocks from symbol_library.dxf (or only system blocks if file missing)."""
    p = path or (assets_dir() / "symbol_library.dxf")
    symlib_log(f"import_symbol_library path={p} exists={p.is_file()}")
    if not p.is_file():
        symlib_log("no symbol_library file; ensuring page ref / checkpoint / wire branch blocks only")
        ensure_cross_page_reference_blocks(doc)
        ensure_checkpoint_block(doc)
        ensure_wire_branch_block(doc)
        return
    src = ezdxf.readfile(str(p))
    ensure_standard_layers(src)
    symlib_log(
        "source block names (non-*): "
        + ", ".join(
            n for n in _iter_block_definition_names(src.blocks) if isinstance(n, str) and not n.startswith("*")
        )[:2000]
    )
    importer = Importer(src, doc)
    imported: list[str] = []
    skipped: list[tuple[str, str]] = []
    for block_name in _iter_block_definition_names(src.blocks):
        if block_name.startswith("*"):
            continue
        try:
            importer.import_block(block_name)
            imported.append(block_name)
        except ezdxf.DXFStructureError as ex:
            skipped.append((block_name, str(ex)))
            continue
    importer.finalize()
    symlib_log(f"merged {len(imported)} blocks into doc: {imported}")
    if skipped:
        symlib_log(f"DXFStructureError on {len(skipped)} blocks (first 5): {skipped[:5]}")
    ensure_cross_page_reference_blocks(doc)
    ensure_checkpoint_block(doc)
    ensure_wire_branch_block(doc)


def reload_symbol_library(doc: Drawing, path: Path | None = None) -> None:
    """Merge or refresh BLOCK definitions from ``symbol_library.dxf`` into *doc*.

    Blocks that **already exist** in *doc* are updated **in place** (entities inside
    the block definition are replaced). INSERT entities keep the same block name, so
    placed symbols redraw with the new geometry without creating ``NAME0`` duplicate
    blocks (unlike calling :func:`import_symbol_library` twice, which relies on
    ``Importer``'s default ``rename=True``).

    Blocks present only in *doc* (not in the library file) are left unchanged.

    Args:
        doc: Target drawing.
        path: Library DXF path. Defaults to ``logic_cad/assets/symbol_library.dxf``.

    Note:
        If *path* does not exist, behavior matches :func:`import_symbol_library`
        (system blocks only; no symbol merges).
    """
    p = path or (assets_dir() / "symbol_library.dxf")
    symlib_log(f"reload_symbol_library path={p} exists={p.is_file()}")
    if not p.is_file():
        import_symbol_library(doc, path=p)
        return
    src = ezdxf.readfile(str(p))
    ensure_standard_layers(src)
    source_names = [
        n
        for n in _iter_block_definition_names(src.blocks)
        if isinstance(n, str) and not n.startswith("*")
    ]
    symlib_log(
        "reload source block names (non-*): "
        + ", ".join(source_names)[:2000]
    )
    to_replace = [n for n in source_names if n in doc.blocks]
    to_add = [n for n in source_names if n not in doc.blocks]
    importer = Importer(src, doc)
    replaced: list[str] = []
    for block_name in to_replace:
        sblk = src.blocks.get(block_name)
        tblk = doc.blocks.get(block_name)
        if sblk is None or tblk is None:
            continue
        if tblk.is_any_layout:
            symlib_log(f"reload_symbol_library skip layout-associated block {block_name!r}")
            continue
        for ent in list(tblk):
            destroy_entity(doc, ent)
        tblk.base_point = sblk.base_point
        sb = sblk.block
        tb = tblk.block
        if sb is not None and tb is not None:
            try:
                tb.dxf.description = sb.dxf.description
            except (AttributeError, ValueError):
                pass
        try:
            importer.import_entities(list(sblk), target_layout=tblk)
        except ezdxf.DXFStructureError as ex:
            symlib_log(f"reload_symbol_library replace {block_name}: {ex}")
            raise
        replaced.append(block_name)
    for block_name in replaced:
        importer.imported_blocks[block_name] = block_name
    imported: list[str] = []
    skipped: list[tuple[str, str]] = []
    for block_name in to_add:
        try:
            importer.import_block(block_name)
            imported.append(block_name)
        except ezdxf.DXFStructureError as ex:
            skipped.append((block_name, str(ex)))
            continue
    importer.finalize()
    symlib_log(
        f"reload_symbol_library: replaced {len(replaced)} merged_new {len(imported)} "
        f"blocks; skipped {len(skipped)}"
    )
    if skipped:
        symlib_log(f"DXFStructureError on reload (first 5): {skipped[:5]}")
    ensure_cross_page_reference_blocks(doc)
    ensure_checkpoint_block(doc)
    ensure_wire_branch_block(doc)
