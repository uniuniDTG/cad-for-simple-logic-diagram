"""Built-in block definitions: page links, in-page links, checkpoint, wire-branch stub."""

from __future__ import annotations

import math

from ezdxf.document import Drawing

from logic_cad.core.dxf.attrib_geometry_sync import sync_insert_attrib_geometry_from_attdefs
from logic_cad.core.dxf.text_style import merge_logic_cad_text_style_attrib
from logic_cad.core.model.constants import (
    BLOCK_CHECKPOINT,
    BLOCK_INPAGE_FROM,
    BLOCK_INPAGE_TO,
    BLOCK_PAGE_FROM,
    BLOCK_PAGE_TO,
    BLOCK_WIRE_BRANCH,
    INPAGE_BLOCK_EXTENT_MM,
    INPAGE_SYM_HEIGHT_MM,
    INPAGE_SYM_INSERT_DY_MM,
    INPAGE_TEXT_GAP_MM,
    LAYER_PORT_IN0_MULTI,
    LAYER_PORT_INOUT0_MULTI,
    LAYER_PORT_OUT0_MULTI,
    LAYER_SYMBOL,
    LAYER_TEXT,
    PAGE_LINK_HEIGHT_MM,
    PAGE_LINK_WIDTH_MM,
    WIRE_BRANCH_RADIUS_MM,
)
from logic_cad.core.model.xdata import get_type


def _add_page_frame_rect(blk: object, w: float, h: float) -> None:
    blk.add_line((0, 0), (w, 0), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((0, h), (w, h), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((0, 0), (0, h), dxfattribs={"layer": LAYER_SYMBOL})
    blk.add_line((w, 0), (w, h), dxfattribs={"layer": LAYER_SYMBOL})


def _add_page_sym_attdef(blk: object, w: float, h: float) -> None:
    blk.add_attdef(
        tag="SYM",
        text="101A",
        insert=(w * 0.12, h * 0.22),
        height=0.34,
        dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
    )


_PAGE_LINK_METADATA_DEGENERATE_EPS_MM = 0.02


def _page_link_metadata_attdef_specs(
    w: float, h: float
) -> tuple[tuple[str, tuple[float, float], float, int], ...]:
    """Return builtin ``PAGE_NAME`` / ``PAGE_DESC`` ATTDEF layout for a *w*×*h* mm frame.

    Args:
        w: Block width (mm), same basis as :func:`_add_page_frame_rect`.
        h: Block height (mm).

    Returns:
        Rows of ``(tag, insert_xy, height, halign)`` matching built-in page-link blocks.
    """

    return (
        ("PAGE_NAME", (w * 0.10, h * 0.80), 0.24, 0),
        ("PAGE_DESC", (w * 0.10, h * 0.58), 0.24, 0),
    )


def _add_page_link_page_name_desc_attdefs(blk: object, w: float, h: float) -> None:
    """Add ``PAGE_NAME`` / ``PAGE_DESC`` ATTDEFs for PAGE_REF sync (invisible until XDATA turns them on).

    Args:
        blk: Block layout for ``PAGE_FROM`` or ``PAGE_TO``.
        w: Block width (mm), same basis as :func:`_add_page_frame_rect`.
        h: Block height (mm).
    """

    for tag, insert_xy, height, halign in _page_link_metadata_attdef_specs(w, h):
        blk.add_attdef(
            tag=tag,
            text="",
            insert=insert_xy,
            height=height,
            dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT, "halign": halign, "invisible": 1}),
        )


def _repair_degenerate_page_link_metadata_attdefs(doc: Drawing) -> bool:
    """Rewrite ``PAGE_NAME`` / ``PAGE_DESC`` ATTDEFs stuck at the block origin.

    Legacy or hand-edited ``PAGE_FROM`` / ``PAGE_TO`` definitions sometimes leave
    metadata ATTDEF inserts at (0, 0). After repair, instance ATTRIBs are synced
    once so UI/PDF match the corrected block definition.

    Args:
        doc: Target drawing.

    Returns:
        True if at least one ATTDEF was modified.
    """

    w_f = float(PAGE_LINK_WIDTH_MM)
    h_f = float(PAGE_LINK_HEIGHT_MM)
    specs: dict[str, tuple[tuple[float, float], float, int]] = {
        tag: (insert_xy, height, halign)
        for tag, insert_xy, height, halign in _page_link_metadata_attdef_specs(w_f, h_f)
    }
    eps = _PAGE_LINK_METADATA_DEGENERATE_EPS_MM
    repaired = False
    for bname in (BLOCK_PAGE_FROM, BLOCK_PAGE_TO):
        if bname not in doc.blocks:
            continue
        for ent in doc.blocks.get(bname):
            if str(ent.dxftype()) != "ATTDEF":
                continue
            tag = str(ent.dxf.tag).upper()
            if tag not in specs:
                continue
            ins = ent.dxf.insert
            if math.hypot(float(ins.x), float(ins.y)) > eps:
                continue
            (ix, iy), height, halign = specs[tag]
            z = float(ins.z)
            ent.dxf.insert = (ix, iy, z)
            ent.dxf.height = height
            ent.dxf.halign = halign
            if ent.dxf.hasattr("align_point"):
                ap = ent.dxf.align_point
                ent.dxf.align_point = (ix, iy, float(ap.z))
            repaired = True
    return repaired


def _sync_page_ref_insert_attrib_geometry(doc: Drawing) -> None:
    """Copy ATTDEF text geometry onto ATTRIBs for every PAGE_REF INSERT on paper layouts.

    Args:
        doc: Drawing to scan (modelspace skipped).
    """

    for layout in doc.layouts:
        if layout.is_modelspace:
            continue
        # Iterates every layout tab (not doc.layouts.get(name)); paper_layout_block not applicable.
        bname = layout.block_record_name
        if bname not in doc.blocks:
            continue
        for ent in doc.blocks.get(bname):
            if ent.dxftype() != "INSERT":
                continue
            if get_type(ent) != "PAGE_REF":
                continue
            sync_insert_attrib_geometry_from_attdefs(doc, ent)


def _add_builtin_page_to(blk: object, w: float, h: float) -> None:
    """Destination page (navigate **to**): input on the left (signal enters this page)."""
    _add_page_frame_rect(blk, w, h)
    blk.add_point((0, h * 0.5), dxfattribs={"layer": "LD_PORT_IN1_LOGIC"})
    _add_page_sym_attdef(blk, w, h)
    _add_page_link_page_name_desc_attdefs(blk, w, h)


def _add_builtin_page_from(blk: object, w: float, h: float) -> None:
    """Source page (**from** here): output on the right (signal leaves toward the other page)."""
    _add_page_frame_rect(blk, w, h)
    blk.add_point((w, h * 0.5), dxfattribs={"layer": "LD_PORT_OUT0_LOGIC"})
    _add_page_sym_attdef(blk, w, h)
    _add_page_link_page_name_desc_attdefs(blk, w, h)


def ensure_cross_page_reference_blocks(doc: Drawing) -> None:
    """Ensure PAGE_TO / PAGE_FROM (library wins when imported)."""
    w, h = PAGE_LINK_WIDTH_MM, PAGE_LINK_HEIGHT_MM
    if BLOCK_PAGE_TO not in doc.blocks:
        blk = doc.blocks.new(BLOCK_PAGE_TO)
        _add_builtin_page_to(blk, w, h)
    if BLOCK_PAGE_FROM not in doc.blocks:
        blk = doc.blocks.new(BLOCK_PAGE_FROM)
        _add_builtin_page_from(blk, w, h)
    if _repair_degenerate_page_link_metadata_attdefs(doc):
        _sync_page_ref_insert_attrib_geometry(doc)


def _add_builtin_inpage_from(blk: object) -> None:
    """Port at origin; ``●※1`` with left-aligned SYM to the right of the port."""
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_IN0_MULTI})
    blk.add_point((0.0, 0.0), dxfattribs={"layer": LAYER_PORT_OUT0_MULTI})
    tx = float(INPAGE_TEXT_GAP_MM)
    ty = float(INPAGE_SYM_INSERT_DY_MM)
    blk.add_attdef(
        tag="SYM",
        text="*1",
        insert=(tx, ty),
        height=float(INPAGE_SYM_HEIGHT_MM),
        dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT, "halign": 0}),
    )


def _add_builtin_inpage_to(blk: object) -> None:
    """``※1●`` with right-aligned SYM left of the port on the right (OUT only)."""
    w = float(INPAGE_BLOCK_EXTENT_MM)
    blk.add_point((w, 0.0), dxfattribs={"layer": LAYER_PORT_OUT0_MULTI})
    tx = w - float(INPAGE_TEXT_GAP_MM)
    ty = float(INPAGE_SYM_INSERT_DY_MM)
    blk.add_attdef(
        tag="SYM",
        text="*1",
        insert=(tx, ty),
        height=float(INPAGE_SYM_HEIGHT_MM),
        dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT, "halign": 2}),
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
        dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
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
        dxfattribs=merge_logic_cad_text_style_attrib({"layer": LAYER_TEXT}),
    )
