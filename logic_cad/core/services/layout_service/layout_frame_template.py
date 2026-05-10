"""Figure frame template: block import, paper INSERT placement, bulk apply from file."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing

from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.dxf.dxf_repository import ensure_standard_layers, load_dxf_with_recover
from logic_cad.core.dxf.dxf_validator import validate as validate_dxf_document
from logic_cad.core.model.constants import (
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
    BLOCK_PAPER_FRAME,
    ENTITY_TYPE_PAPER_FRAME,
)
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    ensure_regapp,
    get_type,
    new_uid,
    set_entity_xdata,
)
from logic_cad.core.pages.page_order import list_paper_layout_names_sorted
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.paper_layout_strip import strip_ld_contents_area_in_paper_block
from logic_cad.core.undo.history import destroy_entity

from .layout_paths import assets_dir, repo_root


def _frame_template_search_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    return [
        assets_dir() / "frame_template.dxf",
        repo_root() / "generate" / "frame_template.dxf",
    ]


_TEMPLATE_BLOCK_NAMES: tuple[str, ...] = (
    BLOCK_PAPER_FRAME,
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
)


def import_frame_template_defined_blocks(doc: Drawing, src: Drawing) -> None:
    """Copy missing frame-template block definitions from *src* into *doc*."""
    imp = Importer(src, doc)
    try:
        for bn in _TEMPLATE_BLOCK_NAMES:
            if bn not in src.blocks or bn in doc.blocks:
                continue
            try:
                imp.import_block(bn)
            except Exception as ex:
                symlib_log(f"frame_template: import_block {bn} ({ex})")
    finally:
        imp.finalize()


def ensure_frame_template_blocks(doc: Drawing, path: Path | None = None) -> bool:
    """Ensure ``LD_PAPER_FRAME`` / ``CONTENTS_*`` blocks exist (from template file if needed)."""
    candidates = _frame_template_search_paths(path)
    chosen: Path | None = None
    for p in candidates:
        if p.is_file():
            chosen = p
            break
    if chosen is None:
        return False
    src = load_dxf_with_recover(chosen, errors="ignore")
    import_frame_template_defined_blocks(doc, src)
    return True


def _replace_frame_template_block_definitions(doc: Drawing, src: Drawing) -> None:
    """Replace ``LD_PAPER_FRAME`` / ``CONTENTS_*`` definitions from *src* (in-place when present)."""
    names_in_src = [n for n in _TEMPLATE_BLOCK_NAMES if n in src.blocks]
    if not names_in_src:
        symlib_log("apply_frame_template: no template blocks in source; skipping block defs")
        return
    to_replace = [n for n in names_in_src if n in doc.blocks]
    to_add = [n for n in names_in_src if n not in doc.blocks]
    importer = Importer(src, doc)
    replaced: list[str] = []
    for block_name in to_replace:
        sblk = src.blocks.get(block_name)
        tblk = doc.blocks.get(block_name)
        if sblk is None or tblk is None:
            continue
        if tblk.is_any_layout:
            symlib_log(f"apply_frame_template skip layout-associated block {block_name!r}")
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
            symlib_log(f"apply_frame_template replace block {block_name}: {ex}")
            raise
        replaced.append(block_name)
    for block_name in replaced:
        importer.imported_blocks[block_name] = block_name
    for block_name in to_add:
        try:
            importer.import_block(block_name)
        except ezdxf.DXFStructureError as ex:
            symlib_log(f"apply_frame_template import_block {block_name}: {ex}")
            raise
    importer.finalize()


def _strip_paper_frame_inserts_from_paper_block(doc: Drawing, blk: object) -> None:
    """Remove top-level ``INSERT`` of ``LD_PAPER_FRAME`` (template / legacy untagged copies)."""
    for e in list(blk):
        if e.dxftype() != "INSERT":
            continue
        if str(e.dxf.name) != BLOCK_PAPER_FRAME:
            continue
        destroy_entity(doc, e)


def validate_frame_template_path(path: Path) -> list[str]:
    """Validate a template DXF before applying it to the current document.

    Args:
        path: Template DXF path selected by the user.

    Returns:
        Validation issue messages. Empty list means the template passed checks.

    Raises:
        FileNotFoundError: If *path* is not an existing file.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    src = load_dxf_with_recover(p, errors="ignore")
    ensure_standard_layers(src)
    ensure_regapp(src)
    return validate_dxf_document(src)


def apply_frame_template_from_path(doc: Drawing, path: Path) -> None:
    """Replace frame template block definitions and re-apply frame INSERT to every paper layout.

    Removes existing app-tagged ``LD_PAPER_FRAME`` inserts on each page, strips top-level
    ``LD_CONTENTS_AREA`` guides, then re-applies frame block references via
    :func:`import_frame_template` before rebuilding TOC grid and frame captions.

    Args:
        doc: Target drawing.
        path: Path to a frame template DXF (same role as ``assets/frame_template.dxf``).

    Raises:
        FileNotFoundError: If *path* is not an existing file.
        ezdxf.DXFStructureError: If the template cannot be imported.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(str(p))
    symlib_log(f"apply_frame_template_from_path path={p}")
    src = load_dxf_with_recover(p, errors="ignore")
    ensure_standard_layers(src)
    _replace_frame_template_block_definitions(doc, src)
    for layout_name in list_paper_layout_names_sorted(doc):
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, layout_name)
        _strip_paper_frame_inserts_from_paper_block(doc, blk)
        strip_ld_contents_area_in_paper_block(doc, blk)
    for layout_name in list_paper_layout_names_sorted(doc):
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        import_frame_template(doc, layout_name, path=p)
    # Deferred import: toc_frame_service imports this package at load time; a top-level
    # import here would create an import cycle (layout_service ↔ toc_frame_service).
    from logic_cad.core.services.toc_frame_service import (
        refresh_all_frame_captions,
        regenerate_toc,
    )

    regenerate_toc(doc)
    refresh_all_frame_captions(doc)
    logic_cad_log("frame", f"apply_frame_template: applied from {p}")


def _paper_frame_attrib_defaults(doc: Drawing) -> dict[str, str]:
    if BLOCK_PAPER_FRAME not in doc.blocks:
        return {}
    out: dict[str, str] = {}
    for ent in doc.blocks.get(BLOCK_PAPER_FRAME):
        if ent.dxftype() == "ATTDEF":
            out[str(ent.dxf.tag)] = str(ent.dxf.text or "")
    return out


def import_frame_template(doc: Drawing, layout_name: str, path: Path | None = None) -> int:
    """Import frame blocks and place one ``LD_PAPER_FRAME`` INSERT on a paper layout.

    Search order when ``path`` is None: ``assets/frame_template.dxf``, then
    ``generate/frame_template.dxf`` at repo root.

    Returns:
        Number of inserted/reused frame blockrefs (0 or 1).
    """
    if layout_name not in doc.layouts:
        symlib_log(f"frame_template: unknown layout {layout_name!r}")
        logic_cad_log("frame", f"template skip: unknown layout {layout_name!r}")
        return 0
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return 0
    blk = paper_layout_block(doc, layout_name)
    candidates = _frame_template_search_paths(path)
    chosen: Path | None = None
    for p in candidates:
        symlib_log(f"frame_template: probe {p} exists={p.is_file()}")
        if p.is_file():
            chosen = p
            break
    if chosen is None:
        symlib_log("frame_template: no template file (tried assets + generate/) — using built-in frame if needed")
        logic_cad_log(
            "frame",
            "template: no file (assets/frame_template.dxf or generate/frame_template.dxf)",
        )
        return 0
    src = load_dxf_with_recover(chosen, errors="ignore")
    import_frame_template_defined_blocks(doc, src)
    if BLOCK_PAPER_FRAME not in doc.blocks:
        symlib_log("frame_template: missing LD_PAPER_FRAME block definition; skip insert")
        return 0
    frame_inserts = [
        e for e in blk if e.dxftype() == "INSERT" and str(getattr(e.dxf, "name", "")) == BLOCK_PAPER_FRAME
    ]
    target_ins = None
    for ins in frame_inserts:
        if get_type(ins) == ENTITY_TYPE_PAPER_FRAME:
            target_ins = ins
            break
    if target_ins is None and frame_inserts:
        target_ins = frame_inserts[0]
    for ins in frame_inserts:
        if ins is target_ins:
            continue
        destroy_entity(doc, ins)
    created = False
    if target_ins is None:
        target_ins = blk.add_blockref(BLOCK_PAPER_FRAME, (0.0, 0.0, 0.0))
        created = True
    defadd = _paper_frame_attrib_defaults(doc)
    if not list(target_ins.attribs) and defadd:
        try:
            target_ins.add_auto_attribs(defadd)
        except Exception as ex:
            symlib_log(f"frame_template: add_auto_attribs ({ex})")
    set_entity_xdata(target_ins, build_ld_app_tags("1", new_uid(), ENTITY_TYPE_PAPER_FRAME))
    symlib_log(
        f"frame_template: {'created' if created else 'reused'} frame insert on layout {layout_name!r}"
    )
    logic_cad_log(
        "frame",
        f"template: applied block-only frame from {chosen} into layout {layout_name!r}",
    )
    return 1
