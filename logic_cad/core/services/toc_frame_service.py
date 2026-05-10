"""Table of contents layouts: grid of ``CONTENTS_*`` INSERTs + paper frame attribs."""

from __future__ import annotations

import re

from ezdxf import bbox
from ezdxf.document import Drawing

from logic_cad.core.attrib_tags import FRAME_ATTDEF_TAGS
from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.model.constants import (
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
    BLOCK_PAPER_FRAME,
    CONTENTS_AREA_DEFAULT_MAXX_MM,
    CONTENTS_AREA_DEFAULT_MAXY_MM,
    CONTENTS_AREA_DEFAULT_MINX_MM,
    CONTENTS_AREA_DEFAULT_MINY_MM,
    CONTENTS_CELL_COL_GAP_MM,
    CONTENTS_CELL_HEIGHT_MM,
    CONTENTS_CELL_ROW_GAP_MM,
    CONTENTS_CELL_WIDTH_MM,
    ENTITY_TYPE_PAPER_FRAME,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    LAYER_CONTENTS_FRAME,
    LAYER_TOC,
    TOC_LAYOUT_NAME,
)
from logic_cad.core.pages.page_layout_meta import (
    read_drawing_number,
    read_drawing_page_start,
    read_drawing_page_total_override,
    read_page_meta,
)
from logic_cad.core.pages.page_order import is_toc_layout_name, toc_layout_names_sorted, toc_page_id_for_slot
from logic_cad.core.pages.toc_contents_layout import contents_area_bbox_mm, toc_grid_cols_and_data_rows
from logic_cad.core.paper_layout_access import paper_layout_block
from logic_cad.core.services.layout_service import (
    LayoutService,
    ensure_frame_template_blocks,
    import_frame_template,
)
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, new_uid, set_entity_xdata

TOC_TEXT_TYPE = "TOC_TEXT"

_PLACEHOLDER_RE = re.compile(r"\{\{(\w+)\}\}")


def expand_frame_placeholders(template: str, mapping: dict[str, str]) -> str:
    """Replace ``{{KEY}}`` substrings using *mapping* (missing keys → empty string)."""

    def repl(m: re.Match[str]) -> str:
        return mapping.get(m.group(1), "")

    return _PLACEHOLDER_RE.sub(repl, template)


def _ensure_layer(doc: Drawing, name: str) -> None:
    if name not in doc.layers:
        doc.layers.add(name)


def _find_paper_frame_insert(blk):
    for e in blk:
        if e.dxftype() != "INSERT":
            continue
        if str(e.dxf.name) != BLOCK_PAPER_FRAME:
            continue
        if get_type(e) != ENTITY_TYPE_PAPER_FRAME:
            continue
        return e
    return None


def _attdef_default_text_by_tag(doc: Drawing, block_name: str) -> dict[str, str]:
    if block_name not in doc.blocks:
        return {}
    out: dict[str, str] = {}
    for ent in doc.blocks.get(block_name):
        if ent.dxftype() == "ATTDEF":
            out[str(ent.dxf.tag)] = str(ent.dxf.text or "")
    return out


def _sync_paper_frame_attribs(ins, doc: Drawing, mapping: dict[str, str]) -> None:
    for a in ins.attribs:
        tag = str(a.dxf.tag).strip().upper()
        if tag not in FRAME_ATTDEF_TAGS:
            continue
        a.dxf.text = mapping.get(tag, "")


def refresh_frame_for_layout(doc: Drawing, layout_name: str) -> None:
    """Update known ATTRIBs on ``PAPER_FRAME`` INSERT only. No insert → no-op."""
    layout = doc.layouts.get(layout_name)
    if layout.is_modelspace:
        return
    blk = paper_layout_block(doc, layout_name)
    ins = _find_paper_frame_insert(blk)
    if ins is None:
        return
    meta = read_page_meta(doc, layout_name)
    pages = LayoutService(doc).list_pages()
    try:
        idx_1 = pages.index(layout_name) + 1
    except ValueError:
        idx_1 = 1
    start = read_drawing_page_start(doc)
    page_num = start + (idx_1 - 1)
    total_ov = read_drawing_page_total_override(doc)
    page_total = total_ov if total_ov is not None else len(pages)
    mapping = {
        "PAGE_NAME": layout_name,
        "PAGE_DESC": meta.get("page_desc", "").strip(),
        "PAGE_REV": meta.get("page_rev", "").strip(),
        "DWG_NO": read_drawing_number(doc),
        "PAGE_NUM": str(page_num),
        "PAGE_TOTAL": str(page_total),
    }
    _sync_paper_frame_attribs(ins, doc, mapping)


def _contents_frame_bbox_size_mm(doc: Drawing, block_name: str) -> tuple[float, float] | None:
    """Axis-aligned size (width, height) from entities on ``LD_CONTENTS_FRAME`` in *block_name*."""
    if block_name not in doc.blocks:
        return None
    blk = doc.blocks.get(block_name)
    ents = [e for e in blk if str(getattr(e.dxf, "layer", "")) == LAYER_CONTENTS_FRAME]
    if not ents:
        return None
    try:
        ext = bbox.extents(ents, fast=True)
        if ext.has_data:
            return float(ext.size.x), float(ext.size.y)
    except Exception:
        pass
    return None


def _toc_cell_metrics_from_contents_frame(doc: Drawing) -> tuple[float, float, float]:
    """``(cell_w, cell_h, header_h)`` for TOC grid from ``LD_CONTENTS_FRAME``; falls back to constants."""
    row_wh = _contents_frame_bbox_size_mm(doc, BLOCK_CONTENTS_ROW)
    hdr_wh = _contents_frame_bbox_size_mm(doc, BLOCK_CONTENTS_HEADER)
    if row_wh is None or hdr_wh is None:
        missing: list[str] = []
        if row_wh is None:
            missing.append(f"{BLOCK_CONTENTS_ROW!r} on {LAYER_CONTENTS_FRAME}")
        if hdr_wh is None:
            missing.append(f"{BLOCK_CONTENTS_HEADER!r} on {LAYER_CONTENTS_FRAME}")
        logic_cad_log(
            "toc",
            "TOC cell size from template: missing " + "; ".join(missing) + "; using CONTENTS_CELL_* defaults",
        )
    rw, rh = row_wh if row_wh else (CONTENTS_CELL_WIDTH_MM, CONTENTS_CELL_HEIGHT_MM)
    hw, hh = hdr_wh if hdr_wh else (CONTENTS_CELL_WIDTH_MM, CONTENTS_CELL_HEIGHT_MM)
    cell_w = max(rw, hw)
    cell_h = rh
    hdr_h = max(hh, cell_h)
    return cell_w, cell_h, hdr_h


def _default_contents_bbox() -> tuple[float, float, float, float]:
    return (
        CONTENTS_AREA_DEFAULT_MINX_MM,
        CONTENTS_AREA_DEFAULT_MINY_MM,
        CONTENTS_AREA_DEFAULT_MAXX_MM,
        CONTENTS_AREA_DEFAULT_MAXY_MM,
    )


def _next_toc_layout_name(doc: Drawing) -> str:
    for i in range(512):
        cand = toc_page_id_for_slot(i)
        if cand not in doc.layouts:
            return cand
    raise RuntimeError("目次用の用紙レイアウトが多すぎます。")


def _clear_generated_toc_entities(doc: Drawing, blk) -> None:
    for e in list(blk):
        if e.dxftype() == "MTEXT" and get_type(e) == TOC_TEXT_TYPE:
            doc.entitydb.delete_entity(e)
            continue
        if e.dxftype() == "MTEXT" and e.dxf.layer == LAYER_TOC:
            doc.entitydb.delete_entity(e)
            continue
        if e.dxftype() == "INSERT":
            t = get_type(e)
            if t in (ENTITY_TYPE_TOC_HEADER, ENTITY_TYPE_TOC_ROW):
                doc.entitydb.delete_entity(e)


def _apply_row_attribs(
    ins,
    doc: Drawing,
    block_name: str,
    mapping: dict[str, str],
) -> None:
    defaults = _attdef_default_text_by_tag(doc, block_name)
    for a in ins.attribs:
        tag = str(a.dxf.tag)
        if tag not in mapping:
            continue
        template = defaults.get(tag, "")
        if "{{" in template:
            a.dxf.text = expand_frame_placeholders(template, mapping)
        else:
            a.dxf.text = mapping[tag]


def _add_contents_header_insert(blk, doc: Drawing, x: float, y: float) -> None:
    ins = blk.add_blockref(BLOCK_CONTENTS_HEADER, (x, y, 0.0), dxfattribs={"layer": LAYER_TOC})
    uid = new_uid()
    set_entity_xdata(ins, build_ld_app_tags("1", uid, ENTITY_TYPE_TOC_HEADER))
    defaults = _attdef_default_text_by_tag(doc, BLOCK_CONTENTS_HEADER)
    if defaults:
        try:
            ins.add_auto_attribs(defaults)
        except Exception:
            pass


def _add_contents_data_row(
    blk,
    doc: Drawing,
    x: float,
    y: float,
    *,
    page_label: str,
    desc: str,
    rev: str,
) -> None:
    ins = blk.add_blockref(BLOCK_CONTENTS_ROW, (x, y, 0.0), dxfattribs={"layer": LAYER_TOC})
    uid = new_uid()
    set_entity_xdata(ins, build_ld_app_tags("1", uid, ENTITY_TYPE_TOC_ROW))
    defaults = _attdef_default_text_by_tag(doc, BLOCK_CONTENTS_ROW)
    if defaults:
        try:
            ins.add_auto_attribs(defaults)
        except Exception:
            pass
    _apply_row_attribs(
        ins,
        doc,
        BLOCK_CONTENTS_ROW,
        {"PAGE_NAME": page_label, "PAGE_DESC": desc, "PAGE_REV": rev},
    )


def _regenerate_toc_mtext_fallback(doc: Drawing, ls: LayoutService, name: str, pages: list[str]) -> None:
    logic_cad_log(
        "toc",
        f"layout={name!r}: using MTEXT TOC fallback (CONTENTS_* grid has no capacity)",
    )
    blk = paper_layout_block(doc, name)
    rows: list[str] = ["page\t説明\t改訂番号"]
    for i, pname in enumerate(pages, start=1):
        m = read_page_meta(doc, pname)
        desc = (m.get("page_desc") or "").strip() or pname
        rev = (m.get("page_rev") or "").strip()
        rows.append(f"{i}\t{desc}\t{rev}")
    body = "\\P".join(rows)
    uid = new_uid()
    mt = blk.add_mtext(
        body,
        dxfattribs={
            "layer": LAYER_TOC,
            "char_height": 2.8,
            "width": 175.0,
            "insert": (18.0, 250.0, 0.0),
            "attachment_point": 1,
        },
    )
    set_entity_xdata(mt, build_ld_app_tags("1", uid, TOC_TEXT_TYPE))


def _place_toc_grid_on_block(
    doc: Drawing,
    blk,
    chunk: list[str],
    bb: tuple[float, float, float, float],
    cell_w: float,
    cell_h: float,
    header_h: float,
) -> None:
    minx, miny, maxx, maxy = bb
    cols, rows_d = toc_grid_cols_and_data_rows(
        minx,
        miny,
        maxx,
        maxy,
        cell_w,
        cell_h,
        header_h,
        CONTENTS_CELL_COL_GAP_MM,
        CONTENTS_CELL_ROW_GAP_MM,
    )
    if cols < 1 or rows_d < 1:
        return
    step_x = cell_w + CONTENTS_CELL_COL_GAP_MM
    step_y = cell_h + CONTENTS_CELL_ROW_GAP_MM
    y_top = maxy
    x0 = minx
    for c in range(cols):
        _add_contents_header_insert(blk, doc, x0 + c * step_x, y_top)
    y_data_top = y_top - header_h - CONTENTS_CELL_ROW_GAP_MM
    cap = cols * rows_d
    padded = list(chunk[:cap]) + [""] * (cap - min(len(chunk), cap))
    # Column-major (N-order): fill each column top-to-bottom, then next column.
    for i, raw in enumerate(padded):
        c = i // rows_d
        r = i % rows_d
        pname = str(raw).strip()
        if not pname:
            page_label = desc = rev = ""
        else:
            meta = read_page_meta(doc, pname)
            page_label = pname
            desc = (meta.get("page_desc") or "").strip() or pname
            rev = (meta.get("page_rev") or "").strip()
        _add_contents_data_row(
            blk,
            doc,
            x0 + c * step_x,
            y_data_top - r * step_y,
            page_label=page_label,
            desc=desc,
            rev=rev,
        )


def regenerate_toc(doc: Drawing, *, toc_name: str | None = None) -> None:
    """Rebuild TOC sheet(s): grid of ``CONTENTS_*`` INSERTs, or MTEXT fallback if no cells fit."""
    _ = toc_name
    _ensure_layer(doc, LAYER_TOC)
    ensure_frame_template_blocks(doc)
    ls = LayoutService(doc)
    pages = [n for n in ls.list_pages() if not is_toc_layout_name(n)]

    if not toc_layout_names_sorted(doc):
        doc.layouts.new(TOC_LAYOUT_NAME)
        ls.ensure_minimal_page(TOC_LAYOUT_NAME)
    elif TOC_LAYOUT_NAME in doc.layouts:
        tblk = paper_layout_block(doc, TOC_LAYOUT_NAME)
        if _find_paper_frame_insert(tblk) is None:
            import_frame_template(doc, TOC_LAYOUT_NAME, path=None)

    for n in toc_layout_names_sorted(doc):
        b = paper_layout_block(doc, n)
        _clear_generated_toc_entities(doc, b)

    if not pages:
        for pname in ls.list_pages():
            refresh_frame_for_layout(doc, pname)
        return

    cell_w, cell_h, hdr_h = _toc_cell_metrics_from_contents_frame(doc)

    default_bb = _default_contents_bbox()
    names_all = toc_layout_names_sorted(doc)
    probe_blk = paper_layout_block(doc, names_all[0])
    raw_probe = contents_area_bbox_mm(probe_blk)
    if raw_probe is None:
        logic_cad_log(
            "toc",
            f"layout={names_all[0]!r}: LD_CONTENTS_AREA missing; using default TOC area bbox",
        )
    probe_bb = raw_probe or default_bb
    cols0, rows_d0 = toc_grid_cols_and_data_rows(
        probe_bb[0],
        probe_bb[1],
        probe_bb[2],
        probe_bb[3],
        cell_w,
        cell_h,
        hdr_h,
        CONTENTS_CELL_COL_GAP_MM,
        CONTENTS_CELL_ROW_GAP_MM,
    )
    if cols0 * rows_d0 < 1:
        _regenerate_toc_mtext_fallback(doc, ls, names_all[0], pages)
        for pname in ls.list_pages():
            refresh_frame_for_layout(doc, pname)
        return

    remaining = list(pages)
    idx = 0

    while remaining:
        if idx >= len(names_all):
            nn = _next_toc_layout_name(doc)
            doc.layouts.new(nn)
            ls.ensure_minimal_page(nn)
            names_all = toc_layout_names_sorted(doc)
        name = names_all[idx]
        blk = paper_layout_block(doc, name)
        raw_bb = contents_area_bbox_mm(blk)
        if raw_bb is None and idx > 0:
            logic_cad_log(
                "toc",
                f"layout={name!r}: LD_CONTENTS_AREA missing; using default TOC area bbox",
            )
        bb = raw_bb or default_bb
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
        if cap < 1:
            _regenerate_toc_mtext_fallback(doc, ls, name, pages)
            for pname in ls.list_pages():
                refresh_frame_for_layout(doc, pname)
            return
        chunk = remaining[:cap]
        remaining = remaining[cap:]
        _place_toc_grid_on_block(doc, blk, chunk, bb, cell_w, cell_h, hdr_h)
        idx += 1

    for name in names_all[idx:]:
        blk = paper_layout_block(doc, name)
        _clear_generated_toc_entities(doc, blk)

    for pname in ls.list_pages():
        refresh_frame_for_layout(doc, pname)


def refresh_all_frame_captions(doc: Drawing) -> None:
    for pname in LayoutService(doc).list_pages():
        refresh_frame_for_layout(doc, pname)
