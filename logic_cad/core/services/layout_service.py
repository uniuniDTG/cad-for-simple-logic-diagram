"""Layouts (pages), frame / virtual viewport."""

from __future__ import annotations

from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    A4_LANDSCAPE_HEIGHT_MM,
    A4_LANDSCAPE_PRINTABLE_80_H_MM,
    A4_LANDSCAPE_PRINTABLE_80_W_MM,
    A4_LANDSCAPE_WIDTH_MM,
    BLOCK_CHECKPOINT,
    BLOCK_INPAGE_FROM,
    BLOCK_INPAGE_TO,
    BLOCK_WIRE_BRANCH,
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
    BLOCK_PAGE_FROM,
    BLOCK_PAGE_TO,
    BLOCK_PAPER_FRAME,
    INPAGE_BLOCK_EXTENT_MM,
    INPAGE_SYM_HEIGHT_MM,
    INPAGE_SYM_INSERT_DY_MM,
    INPAGE_TEXT_GAP_MM,
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_PAPER_FRAME,
    ENTITY_TYPE_WIRE_BRANCH_HATCH,
    LAYER_CONTENTS_AREA,
    LAYER_FRAME,
    LAYER_PORT_INOUT0_MULTI,
    LAYER_PORT_IN0_MULTI,
    LAYER_PORT_OUT0_MULTI,
    LAYER_SYMBOL,
    LAYER_TEXT,
    LAYER_VIEWPORTS,
    WIRE_BRANCH_RADIUS_MM,
    LAYER_VPORT,
    PAGE_LINK_HEIGHT_MM,
    PAGE_LINK_WIDTH_MM,
    PEER_UID_XDATA,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.dxf.dxf_repository import ensure_standard_layers, load_dxf_with_recover
from logic_cad.core.dxf.dxf_validator import validate as validate_dxf_document
from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.debug.debug_symlib import symlib_log
from logic_cad.core.pages.page_layout_meta import merge_layout_page_xdata, read_page_meta
from logic_cad.core.pages.page_order import (
    is_reserved_toc_page_id,
    is_toc_layout_name,
    list_paper_layout_names_sorted,
    validate_paper_layout_name,
)
from logic_cad.core.undo.history import destroy_entity
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.pages.page_ref import (
    reconnect_page_ref_peers_after_foreign_import,
    refresh_all_page_ref_syms,
    refresh_page_ref_syms_on_layout,
    remap_page_refs,
)
from logic_cad.core.model.xdata import (
    build_ld_app_tags,
    ensure_regapp,
    get_type,
    get_uid,
    new_uid,
    read_ld_app_dict,
    set_entity_xdata,
)


def _assets_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "assets"


def _repo_root() -> Path:
    """Repository root (parent of ``logic_cad`` package)."""
    return Path(__file__).resolve().parents[3]


def _frame_template_search_paths(explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit]
    return [
        _assets_dir() / "frame_template.dxf",
        _repo_root() / "generate" / "frame_template.dxf",
    ]


_TEMPLATE_BLOCK_NAMES: tuple[str, ...] = (
    BLOCK_PAPER_FRAME,
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
)

# Built-in blocks: not user-placeable from the palette (TOC grid / page links use dedicated UI).
_PALETTE_EXCLUDED_SYSTEM_BLOCKS: frozenset[str] = frozenset(
    {
        BLOCK_CONTENTS_HEADER,
        BLOCK_CONTENTS_ROW,
        BLOCK_PAGE_FROM,
        BLOCK_PAGE_TO,
        BLOCK_INPAGE_FROM,
        BLOCK_INPAGE_TO,
        BLOCK_WIRE_BRANCH,
    }
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


def _strip_ld_contents_area_top_level(doc: Drawing, blk) -> None:
    """Remove top-level paper-space entities on ``LD_CONTENTS_AREA``."""
    for e in list(blk):
        if str(e.dxf.layer) != LAYER_CONTENTS_AREA:
            continue
        try:
            blk.delete_entity(e)
        except Exception as ex:
            symlib_log(f"frame_template: strip contents area {e}: {ex}")
            try:
                doc.entitydb.delete_entity(e)
            except Exception as ex2:
                symlib_log(f"frame_template: entitydb.delete_entity {e}: {ex2}")


def strip_ld_contents_area_all_paper_layouts(doc: Drawing) -> None:
    """Remove top-level ``LD_CONTENTS_AREA`` guide geometry from every paper layout block."""
    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        blk = doc.blocks.get(layout.block_record_name)
        _strip_ld_contents_area_top_level(doc, blk)


def _lw_closed_rect_width_height_mm(entity) -> tuple[float, float] | None:
    """Axis-aligned closed LWPOLYLINE with 4 corners → (width, height), else None."""
    if entity.dxftype() != "LWPOLYLINE":
        return None
    try:
        if not entity.closed:
            return None
    except Exception:
        return None
    try:
        pts = [p[:2] for p in entity.get_points("xyb")]
    except Exception:
        return None
    if len(pts) not in (4, 5):
        return None
    if len(pts) == 5 and (pts[0][0] != pts[4][0] or pts[0][1] != pts[4][1]):
        return None
    if len(pts) == 5:
        pts = pts[:4]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    w = max(xs) - min(xs)
    h = max(ys) - min(ys)
    return (w, h)


def _matches_printable_80_rect(w: float, h: float, tol: float = 0.75) -> bool:
    """CAD default inner frame: 80% of A4 landscape (e.g. 237.6 × 168.0 mm)."""
    ew, eh = A4_LANDSCAPE_PRINTABLE_80_W_MM, A4_LANDSCAPE_PRINTABLE_80_H_MM
    return (abs(w - ew) < tol and abs(h - eh) < tol) or (abs(w - eh) < tol and abs(h - ew) < tol)


def _ensure_viewports_layer_off(doc: Drawing) -> None:
    """CAD layer for paper VIEWPORT entities; off so viewport borders are hidden."""
    if LAYER_VIEWPORTS not in doc.layers:
        doc.layers.add(LAYER_VIEWPORTS)
    doc.layers.get(LAYER_VIEWPORTS).off()


def _ensure_single_main_viewport_hidden(doc: Drawing, layout) -> None:
    """Keep exactly one main paper VIEWPORT (CAD expectation) on LAYER_VIEWPORTS (layer off)."""
    _ensure_viewports_layer_off(doc)
    main = layout.main_viewport()
    if main is None:
        for vp in list(layout.viewports()):
            try:
                layout.delete_entity(vp)
            except Exception as ex:
                symlib_log(f"paper_layout: drop orphan viewport {vp}: {ex}")
        try:
            layout.add_new_main_viewport()
        except Exception as ex:
            symlib_log(f"paper_layout: add_new_main_viewport failed: {ex}")
            return
    else:
        for vp in list(layout.viewports()):
            if vp.dxf.handle == main.dxf.handle:
                continue
            try:
                layout.delete_entity(vp)
            except Exception as ex:
                symlib_log(f"paper_layout: could not delete extra viewport {vp}: {ex}")
    main = layout.main_viewport()
    if main is None:
        return
    main.dxf.layer = LAYER_VIEWPORTS
    try:
        layout.set_current_viewport_handle(main.dxf.handle)
    except Exception as ex:
        symlib_log(f"paper_layout: set_current_viewport_handle failed: {ex}")


def _remove_layer0_printable_decoys(layout) -> None:
    """Drop layer-'0' closed rects matching default 10%-margin printable area (noise in BricsCAD)."""
    blk = layout.doc.blocks.get(layout.block_record_name)
    for e in list(blk):
        if str(e.dxf.layer) != "0":
            continue
        wh = _lw_closed_rect_width_height_mm(e)
        if wh is None:
            continue
        w, h = wh
        if _matches_printable_80_rect(w, h):
            try:
                layout.delete_entity(e)
            except Exception as ex:
                symlib_log(f"paper_layout: could not delete layer-0 decoy rect {e}: {ex}")


def configure_paper_layout_a4_landscape(doc: Drawing, layout_name: str) -> None:
    """BricsCAD/AutoCAD: set plot paper to A4 landscape and align limits to (0,0)–(W,H).

    Keeps a single main paper-space VIEWPORT (model window) for CAD compatibility, moves it
    to ``VIEWPORTS``, and turns that layer off so the viewport frame is not visible. Logic
    CAD still uses ``LD_VPORT`` LWPOLYLINE for its own page/view semantics.
    """
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    dxf = layout.dxf_layout.dxf
    dxf.paper_width = A4_LANDSCAPE_WIDTH_MM
    dxf.paper_height = A4_LANDSCAPE_HEIGHT_MM
    dxf.paper_size = "A4"
    dxf.left_margin = 0
    dxf.right_margin = 0
    dxf.top_margin = 0
    dxf.bottom_margin = 0
    dxf.plot_origin_x_offset = 0
    dxf.plot_origin_y_offset = 0
    dxf.plot_paper_units = 1

    _ensure_single_main_viewport_hidden(doc, layout)

    try:
        layout.plot_viewport_borders(False)
    except Exception as ex:
        symlib_log(f"paper_layout: plot_viewport_borders(False) failed: {ex}")
    _remove_layer0_printable_decoys(layout)

    layout.reset_paper_limits()
    layout.reset_extents()


def _iter_block_definition_names(blocks_section) -> list[str]:
    """Block name strings (ezdxf iter may yield str or BlockLayout depending on version)."""
    names_method = getattr(blocks_section, "names", None)
    if callable(names_method):
        try:
            return [n for n in names_method() if isinstance(n, str)]
        except (TypeError, AttributeError):
            pass
    out: list[str] = []
    for item in blocks_section:
        name = item if isinstance(item, str) else getattr(item.dxf, "name", str(item))
        out.append(name)
    return out


def list_palette_block_names(doc: Drawing) -> list[str]:
    """Block definitions to offer on the palette (excludes layout helpers and gate stubs)."""
    out: list[str] = []
    for name in sorted(_iter_block_definition_names(doc.blocks)):
        if name.startswith("*"):
            continue
        if name == "PAGE_LINK":
            continue
        un = name.upper()
        if un.startswith("AND_") or un.startswith("OR_"):
            continue
        if name.startswith("_"):
            continue
        if name == BLOCK_PAPER_FRAME:
            continue
        if name in _PALETTE_EXCLUDED_SYSTEM_BLOCKS:
            continue
        if un == "LD_CHECKPOINT":
            continue
        out.append(name)
    return out


def import_symbol_library(doc: Drawing, path: Path | None = None) -> None:
    """Merge blocks from symbol_library.dxf (or only system blocks if file missing)."""
    p = path or (_assets_dir() / "symbol_library.dxf")
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
    p = path or (_assets_dir() / "symbol_library.dxf")
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


def _strip_paper_frame_inserts_from_paper_block(doc: Drawing, blk) -> None:
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
        blk = doc.blocks.get(layout.block_record_name)
        _strip_paper_frame_inserts_from_paper_block(doc, blk)
        _strip_ld_contents_area_top_level(doc, blk)
    for layout_name in list_paper_layout_names_sorted(doc):
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        import_frame_template(doc, layout_name, path=p)
    from logic_cad.core.services.toc_frame_service import (
        refresh_all_frame_captions,
        regenerate_toc,
    )

    regenerate_toc(doc)
    refresh_all_frame_captions(doc)
    logic_cad_log("frame", f"apply_frame_template: applied from {p}")


def _add_page_frame_rect(blk, w: float, h: float) -> None:
    blk.add_line((0, 0), (w, 0), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((0, h), (w, h), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((0, 0), (0, h), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((w, 0), (w, h), dxfattribs={"layer": LAYER_SYMBOL})


def _add_page_sym_attdef(blk, w: float, h: float) -> None:
    blk.add_attdef(
        tag="SYM",
        text="101A",
        insert=(w * 0.12, h * 0.22),
        height=0.34,
        dxfattribs={"layer": LAYER_TEXT},
    )


def _add_builtin_page_to(blk, w: float, h: float) -> None:
    """Destination page (navigate **to**): input on the left (signal enters this page)."""
    _add_page_frame_rect(blk, w, h)
    blk.add_point((0, h * 0.5), dxfattribs={"layer": "LD_PORT_IN1_LOGIC"})
    _add_page_sym_attdef(blk, w, h)


def _add_builtin_page_from(blk, w: float, h: float) -> None:
    """Source page (**from** here): output on the right (signal leaves toward the other page)."""
    _add_page_frame_rect(blk, w, h)
    blk.add_point((w, h * 0.5), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
    _add_page_sym_attdef(blk, w, h)


def ensure_cross_page_reference_blocks(doc: Drawing) -> None:
    """Ensure PAGE_TO / PAGE_FROM (library wins when imported)."""
    w, h = PAGE_LINK_WIDTH_MM, PAGE_LINK_HEIGHT_MM
    if BLOCK_PAGE_TO not in doc.blocks:
        blk = doc.blocks.new(BLOCK_PAGE_TO)
        _add_builtin_page_to(blk, w, h)
    if BLOCK_PAGE_FROM not in doc.blocks:
        blk = doc.blocks.new(BLOCK_PAGE_FROM)
        _add_builtin_page_from(blk, w, h)


def _add_builtin_inpage_from(blk) -> None:
    """Port at origin; ``●※1`` with left-aligned SYM to the right of the port."""
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_IN0_MULTI})
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_OUT0_MULTI})
    tx = float(INPAGE_TEXT_GAP_MM)
    ty = float(INPAGE_SYM_INSERT_DY_MM)
    blk.add_attdef(
        tag="SYM",
        text="※1",
        insert=(tx, ty),
        height=float(INPAGE_SYM_HEIGHT_MM),
        dxfattribs={"layer": LAYER_TEXT, "halign": 0},
    )


def _add_builtin_inpage_to(blk) -> None:
    """``※1●`` with right-aligned SYM left of the port on the right (OUT only)."""
    w = float(INPAGE_BLOCK_EXTENT_MM)
    blk.add_point((w, 0.0), dxfattribs={"layer": LAYER_PORT_OUT0_MULTI})
    tx = w - float(INPAGE_TEXT_GAP_MM)
    ty = float(INPAGE_SYM_INSERT_DY_MM)
    blk.add_attdef(
        tag="SYM",
        text="※1",
        insert=(tx, ty),
        height=float(INPAGE_SYM_HEIGHT_MM),
        dxfattribs={"layer": LAYER_TEXT, "halign": 2},
    )


def ensure_inpage_reference_blocks(doc: Drawing) -> None:
    """Ensure INPAGE_FROM / INPAGE_TO (checkpoint-like ports + SYM only)."""
    if BLOCK_INPAGE_FROM not in doc.blocks:
        blk = doc.blocks.new(BLOCK_INPAGE_FROM)
        _add_builtin_inpage_from(blk)
    if BLOCK_INPAGE_TO not in doc.blocks:
        blk = doc.blocks.new(BLOCK_INPAGE_TO)
        _add_builtin_inpage_to(blk)


def ensure_checkpoint_block(doc: Drawing) -> None:
    """Ensure ``LD_CHECKPOINT`` exists (POINT IN0/OUT0 MULTI at same origin; optional SYM)."""
    if BLOCK_CHECKPOINT in doc.blocks:
        return
    blk = doc.blocks.new(BLOCK_CHECKPOINT)
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_IN0_MULTI})
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_OUT0_MULTI})
    blk.add_attdef(
        tag="SYM",
        text="CP_1",
        insert=(0.25, 0.35),
        height=0.28,
        dxfattribs={"layer": LAYER_TEXT},
    )


def ensure_wire_branch_block(doc: Drawing) -> None:
    """Ensure ``LD_WIRE_BRANCH`` exists (INOUT0_MULTI at origin; circle glyph; SYM)."""
    if BLOCK_WIRE_BRANCH in doc.blocks:
        return
    blk = doc.blocks.new(BLOCK_WIRE_BRANCH)
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_INOUT0_MULTI})
    r = float(WIRE_BRANCH_RADIUS_MM)
    blk.add_circle((0.0, 0.0), r, dxfattribs={"layer": LAYER_SYMBOL, "color": 7})
    hatch = blk.add_hatch(color=7, dxfattribs={"layer": LAYER_SYMBOL})
    ep = hatch.paths.add_edge_path()
    ep.add_arc(center=(0.0, 0.0), radius=r, start_angle=0, end_angle=360)
    blk.add_attdef(
        tag="SYM",
        text="BR_1",
        insert=(0.35, 0.55),
        height=0.22,
        dxfattribs={"layer": LAYER_TEXT},
    )


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
    blk = doc.blocks.get(layout.block_record_name)
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


def remap_layout_block_ld_uids(dest_blk: object, old_to_new: dict[str, str]) -> None:
    """Apply *old_to_new* uid map to LD-tagged entities in a paper layout block.

    Phase 1 assigns new ``uid`` in XDATA on every mapped entity; phase 2 remaps ``WIRE``,
    ``WIRE_ALIAS``, wire-branch hatch dependencies, ``INPAGE_REF``, and ``PAGE_REF`` peer
    UIDs embedded in dictionaries.

    Args:
        dest_blk: Block layout (paperspace layout block record).
        old_to_new: Mapping from previously collected UIDs to new UIDs.
    """
    for ent in list(dest_blk):
        u = get_uid(ent)
        if not u:
            continue
        nu = old_to_new.get(u)
        if not nu:
            continue
        d = read_ld_app_dict(ent)
        t = get_type(ent) or "SYM"
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        set_entity_xdata(ent, build_ld_app_tags("1", nu, t, extra))

    for ent in list(dest_blk):
        t = get_type(ent)
        if not t:
            continue
        d = read_ld_app_dict(ent)
        nu = d.get("uid")
        if not nu:
            continue
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        if t == "WIRE":
            su, du = extra.get("src"), extra.get("dst")
            if su in old_to_new:
                extra["src"] = old_to_new[su]
            if du in old_to_new:
                extra["dst"] = old_to_new[du]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, "WIRE", extra))
        elif t == ENTITY_TYPE_WIRE_BRANCH_HATCH:
            b = extra.get("branch")
            if b in old_to_new:
                extra["branch"] = old_to_new[b]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, ENTITY_TYPE_WIRE_BRANCH_HATCH, extra))
        elif t == "WIRE_ALIAS":
            w = extra.get("wire")
            if w in old_to_new:
                extra["wire"] = old_to_new[w]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, "WIRE_ALIAS", extra))
        elif t == ENTITY_TYPE_INPAGE_REF:
            p = (extra.get(PEER_UID_XDATA) or "").strip()
            if p in old_to_new:
                extra[PEER_UID_XDATA] = old_to_new[p]
            set_entity_xdata(ent, build_ld_app_tags("1", nu, ENTITY_TYPE_INPAGE_REF, extra))
        elif t == "PAGE_REF":
            peer = (extra.get(PEER_UID_XDATA) or "").strip()
            if peer in old_to_new:
                extra[PEER_UID_XDATA] = old_to_new[peer]
                set_entity_xdata(ent, build_ld_app_tags("1", nu, "PAGE_REF", extra))


class LayoutService:
    def __init__(self, doc: Drawing) -> None:
        self.doc = doc

    def list_pages(self) -> list[str]:
        return list_paper_layout_names_sorted(self.doc)

    def suggest_next_layout_name(self) -> str:
        """Next default paper layout name (numeric, not reserved for TOC slots)."""
        used = {L.name for L in self.doc.layouts if not L.is_modelspace}
        n = 10
        while str(n) in used or is_reserved_toc_page_id(str(n)):
            n += 1
        return str(n)

    def ensure_minimal_page(self, layout_name: str) -> None:
        """LAYOUT XDATA + optional ``import_frame_template`` when no ``LD_VPORT`` VPORT polyline.

        Does not synthesize ``LD_FRAME`` / ``LD_VPORT``; those come from the template or user CAD only.
        Page identity is ``layout_name`` only; XDATA keeps ``page_desc`` / ``page_rev`` if present.
        """
        layout = self.doc.layouts.get(layout_name)
        if layout.is_modelspace:
            return
        br = layout.block_record_name
        blk = self.doc.blocks.get(br)
        le = layout.dxf_layout
        d = read_ld_app_dict(le)
        uid = d.get("uid") or new_uid()
        extra = {k: v for k, v in d.items() if k in ("page_desc", "page_rev")}
        tags = build_ld_app_tags("1", uid, "PAGE", extra)
        set_entity_xdata(le, tags)



        has_v = any(
            e.dxftype() == "LWPOLYLINE"
            and e.dxf.layer == LAYER_VPORT
            and get_type(e) == "VPORT"
            for e in blk
        )
        if not has_v:
            import_frame_template(self.doc, layout_name, path=None)

        configure_paper_layout_a4_landscape(self.doc, layout_name)

    def rename_page(self, old: str, new: str) -> None:
        """Rename a paper layout and update PAGE_REF targets."""
        if old == new:
            return
        validate_paper_layout_name(new)
        self.doc.layouts.rename(old, new)
        remap_page_refs(self.doc, old, new, self.list_pages())

    def add_page(self, name: str) -> None:
        validate_paper_layout_name(name)
        if name in self.doc.layouts:
            raise ValueError(f"レイアウト {name!r} は既に存在します。")
        self.doc.layouts.new(name)
        self.ensure_minimal_page(name)

    def _remove_page_refs_to_target(self, target_layout: str) -> None:
        """Delete PAGE_REF inserts on all paperspace layouts that link to *target_layout*."""
        for layout in self.doc.layouts:
            if layout.is_modelspace:
                continue
            blk = self.doc.blocks.get(layout.block_record_name)
            for e in list(blk):
                if e.dxftype() != "INSERT":
                    continue
                if get_type(e) != "PAGE_REF":
                    continue
                d = read_ld_app_dict(e)
                if (d.get(TARGET_LAYOUT_XDATA) or "").strip() != target_layout:
                    continue
                destroy_entity(self.doc, e)

    def delete_page(self, layout_name: str) -> None:
        """Remove a paperspace layout and any cross-page refs pointing to it."""
        if layout_name not in self.doc.layouts:
            raise ValueError(f"レイアウト {layout_name!r} がありません。")
        layout = self.doc.layouts.get(layout_name)
        if layout.is_modelspace:
            raise ValueError("モデル空間は削除できません")
        papers = list_paper_layout_names_sorted(self.doc)
        if len(papers) <= 1:
            raise ValueError("最後の1枚の用紙レイアウトは削除できません")
        if layout_name not in papers:
            raise ValueError(f"レイアウト {layout_name!r} は用紙レイアウトではありません。")
        self._remove_page_refs_to_target(layout_name)
        self.doc.layouts.delete(layout_name)
        refresh_all_page_ref_syms(self.doc)

    def suggest_import_dest_layout_name(self, desired: str) -> str:
        """Return *desired* if unused; else a unique paper layout name for import.

        Args:
            desired: Preferred layout name from the source document.

        Returns:
            A name valid for ``layouts.new`` in this document.
        """
        validate_paper_layout_name(desired)
        if desired not in self.doc.layouts:
            return desired
        base = f"{desired}_imp"
        name = base
        n = 1
        while name in self.doc.layouts:
            name = f"{base}{n}"
            n += 1
        validate_paper_layout_name(name)
        return name

    def import_paper_layouts_from_foreign_drawing(
        self,
        foreign_doc: Drawing,
        migrations: list[tuple[str, str]],
    ) -> list[str]:
        """Copy paper layouts from *foreign_doc* into this document with new UIDs.

        Dependent block definitions are merged with :class:`~ezdxf.addons.importer.Importer`
        (:meth:`~ezdxf.addons.importer.Importer.import_block`); layout contents are cloned with
        ``entity.copy()`` like :meth:`duplicate_paper_layout` so LD XDATA is preserved.
        PAGE_REF ``peer_uid`` is fixed on imported sheets by :func:`reconnect_page_ref_peers_after_foreign_import`
        when the partner INSERT exists on the destination drawing (``TARGET_LAYOUT`` / ranks are not rewritten).

        Args:
            foreign_doc: Source drawing (read-only use; not modified structurally here).
            migrations: Pairs ``(source_layout_name, dest_layout_name)`` to create.

        Returns:
            List of ``dest_layout_name`` values created, in *migrations* order.

        Raises:
            ValueError: Invalid names, missing source layout, or destination already exists.
        """
        if not migrations:
            return []
        dest_names = [d for _, d in migrations]
        if len(dest_names) != len(set(dest_names)):
            raise ValueError("取り込み先のレイアウト名が重複しています。")
        for src, dst in migrations:
            if is_toc_layout_name(src):
                raise ValueError(f"目次用レイアウト {src!r} は取り込めません。")
            validate_paper_layout_name(dst)
            if src not in foreign_doc.layouts:
                raise ValueError(f"ソースにレイアウト {src!r} がありません。")
            if dst in self.doc.layouts:
                raise ValueError(f"レイアウト {dst!r} は既に存在します。")
            sl = foreign_doc.layouts.get(src)
            if sl.is_modelspace:
                raise ValueError(f"レイアウト {src!r} はモデル空間です。")
            papers_f = list_paper_layout_names_sorted(foreign_doc)
            if src not in papers_f:
                raise ValueError(f"レイアウト {src!r} は用紙レイアウトではありません。")

        ensure_cross_page_reference_blocks(self.doc)
        insert_blocks_needed: set[str] = set()
        for src, _dst in migrations:
            src_layout = foreign_doc.layouts.get(src)
            src_blk0 = foreign_doc.blocks.get(src_layout.block_record_name)
            for e in src_blk0:
                if e.dxftype() == "INSERT":
                    insert_blocks_needed.add(str(e.dxf.name))

        importer = Importer(foreign_doc, self.doc)
        for bname in sorted(insert_blocks_needed):
            if bname not in foreign_doc.blocks:
                logic_cad_log("layout", f"import_pages: unknown block reference {bname!r}")
                continue
            if bname in self.doc.blocks:
                continue
            try:
                importer.import_block(bname)
            except Exception as ex:
                logic_cad_log("layout", f"import_block {bname!r}: {ex}")
                raise ValueError(f"ブロック定義 {bname!r} を取り込めませんでした。") from ex
        importer.finalize()

        created: list[str] = []
        for src, dst in migrations:
            self.doc.layouts.new(dst)
            self.ensure_minimal_page(dst)
            dest_layout = self.doc.layouts.get(dst)
            dest_blk = self.doc.blocks.get(dest_layout.block_record_name)
            for ent in list(dest_blk):
                destroy_entity(self.doc, ent)
            src_layout = foreign_doc.layouts.get(src)
            src_blk = foreign_doc.blocks.get(src_layout.block_record_name)
            for e in list(src_blk):
                try:
                    ne = e.copy()
                    dest_blk.add_entity(ne)
                except Exception as ex:
                    logic_cad_log("layout", f"import_page copy skip {e.dxftype()}: {ex}")
            created.append(dst)

        old_to_new: dict[str, str] = {}
        for dst in created:
            blk = self.doc.blocks.get(self.doc.layouts.get(dst).block_record_name)
            for ent in blk:
                u = get_uid(ent)
                if u and u not in old_to_new:
                    old_to_new[u] = new_uid()
        for dst in created:
            blk = self.doc.blocks.get(self.doc.layouts.get(dst).block_record_name)
            remap_layout_block_ld_uids(blk, old_to_new)

        for src, dst in migrations:
            meta = read_page_meta(foreign_doc, src)
            desc_raw = str(meta.get("page_desc") or "").strip()
            rev_raw = str(meta.get("page_rev") or "").strip()
            merge_layout_page_xdata(
                self.doc,
                dst,
                page_desc=desc_raw if desc_raw else None,
                page_rev=rev_raw if rev_raw else None,
            )

        src_to_dest = {s: d for s, d in migrations}
        reconnect_page_ref_peers_after_foreign_import(self.doc, src_to_dest, created)
        for dst in created:
            refresh_page_ref_syms_on_layout(self.doc, dst)
            refresh_inpage_ref_syms_on_layout(self.doc, dst)
        return created

    def duplicate_paper_layout(self, source_name: str, dest_name: str) -> None:
        """Clone *source_name* paper block into a new layout *dest_name* (new UIDs; WIRE src/dst remapped)."""
        if is_toc_layout_name(source_name):
            raise ValueError("目次用レイアウト（0, 0A …）は複製できません。")
        validate_paper_layout_name(dest_name)
        if dest_name in self.doc.layouts:
            raise ValueError(f"レイアウト {dest_name!r} は既に存在します")
        if source_name not in self.doc.layouts:
            raise ValueError(f"レイアウト {source_name!r} がありません")
        src_layout = self.doc.layouts.get(source_name)
        if src_layout.is_modelspace:
            raise ValueError("モデル空間は複製できません")
        papers = list_paper_layout_names_sorted(self.doc)
        if source_name not in papers:
            raise ValueError(f"レイアウト {source_name!r} は用紙レイアウトではありません")

        self.doc.layouts.new(dest_name)
        self.ensure_minimal_page(dest_name)

        dest_layout = self.doc.layouts.get(dest_name)
        dest_blk = self.doc.blocks.get(dest_layout.block_record_name)
        for e in list(dest_blk):
            destroy_entity(self.doc, e)

        src_blk = self.doc.blocks.get(src_layout.block_record_name)
        for e in list(src_blk):
            try:
                ne = e.copy()
                dest_blk.add_entity(ne)
            except Exception as ex:
                logic_cad_log("layout", f"duplicate_page skip {e.dxftype()}: {ex}")

        old_to_new: dict[str, str] = {}
        for e in list(dest_blk):
            u = get_uid(e)
            if not u or u in old_to_new:
                continue
            old_to_new[u] = new_uid()

        remap_layout_block_ld_uids(dest_blk, old_to_new)

        refresh_page_ref_syms_on_layout(self.doc, dest_name)
        refresh_inpage_ref_syms_on_layout(self.doc, dest_name)
