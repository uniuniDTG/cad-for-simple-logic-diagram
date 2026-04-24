"""Off-screen pixmap for palette QDrag (symbol-shaped preview, not default '+' cursor)."""

from __future__ import annotations

import math

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    BLOCK_CHECKPOINT,
    BLOCK_INPAGE_FROM,
    BLOCK_PAGE_FROM,
    BLOCK_WIRE_BRANCH,
)
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory
from logic_cad.core.services.layout_service import (
    ensure_checkpoint_block,
    ensure_cross_page_reference_blocks,
    ensure_inpage_reference_blocks,
    ensure_wire_branch_block,
)
from logic_cad.core.services.symbol_service import uniform_scale_for_block
from logic_cad.ui.block_paint import (
    block_scaled_bounds_with_instance,
    glyph_upright_extra_deg,
    paint_block_definition,
)


def _resolve_block_for_payload(doc: Drawing, payload: str) -> tuple[str, str] | None:
    """Return (block_name, sym_display_text_for_bounds) or None."""
    kind, sep, name = payload.partition(":")
    if not sep:
        return None
    gates = DynamicGateFactory()
    if kind == "kind":
        if name == "AND":
            b = gates.ensure_and_block(doc, 2)
            return b, "AND_1"
        if name == "OR":
            b = gates.ensure_or_block(doc, 2)
            return b, "OR_1"
        if name == "CHECKPOINT":
            ensure_checkpoint_block(doc)
            if BLOCK_CHECKPOINT not in doc.blocks:
                return None
            return BLOCK_CHECKPOINT, "CP_1"
        if name == "WIRE_BRANCH":
            ensure_wire_branch_block(doc)
            if BLOCK_WIRE_BRANCH not in doc.blocks:
                return None
            return BLOCK_WIRE_BRANCH, "BR_1"
        return None
    if kind == "page_link":
        ensure_cross_page_reference_blocks(doc)
        if BLOCK_PAGE_FROM not in doc.blocks:
            return None
        return BLOCK_PAGE_FROM, ""
    if kind == "inpage_link":
        ensure_inpage_reference_blocks(doc)
        if BLOCK_INPAGE_FROM not in doc.blocks:
            return None
        return BLOCK_INPAGE_FROM, "※1"
    if kind == "block":
        if not name or name not in doc.blocks:
            return None
        return name, name
    return None


def palette_drag_pixmap_and_hotspot(
    doc: Drawing | None,
    payload: str,
    *,
    list_label: str = "",
    max_side_px: int = 88,
) -> tuple[QPixmap | None, QPoint]:
    """Build a transparent pixmap of the symbol and a hotspot (pixmap center)."""
    if doc is None or not payload:
        return None, QPoint(0, 0)
    resolved = _resolve_block_for_payload(doc, payload)
    if resolved is None:
        return None, QPoint(0, 0)
    block_name, sym_default = resolved
    kind, sep, name = payload.partition(":")
    is_gate_payload = kind == "kind" and name in ("AND", "OR")
    if sym_default and is_gate_payload:
        sym_text = sym_default
    else:
        sym_text = (list_label.strip() or sym_default) if sym_default else list_label.strip()
    scale = uniform_scale_for_block(doc, block_name)
    g_extra = glyph_upright_extra_deg(0.0)
    bounds = block_scaled_bounds_with_instance(
        doc,
        block_name,
        scale,
        scale,
        glyph_extra_deg=g_extra,
        sym_display_text=sym_text,
        sym_tag_visible=True,
        instance_attribs=None,
    )
    if bounds is None or bounds.isEmpty():
        return None, QPoint(0, 0)

    bw = max(float(bounds.width()), 1e-6)
    bh = max(float(bounds.height()), 1e-6)
    inner = max(8, max_side_px - 4)
    s = min(inner / bw, inner / bh)
    pw = max(1, int(math.ceil(bw * s)) + 4)
    ph = max(1, int(math.ceil(bh * s)) + 4)

    pm = QPixmap(pw, ph)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = float(bounds.center().x())
    cy = float(bounds.center().y())
    p.translate(pw / 2.0, ph / 2.0)
    p.scale(s, s)
    p.translate(-cx, -cy)
    # paint_block_strokes inherits painter.pen(); default is black — use white for drag ghost.
    _drag_pen = QPen(QColor(255, 255, 255))
    _drag_pen.setCosmetic(True)
    _drag_pen.setWidthF(0)
    p.setPen(_drag_pen)
    painted = paint_block_definition(
        p,
        doc,
        block_name,
        scale_x=scale,
        scale_y=scale,
        glyph_extra_deg=g_extra,
        sym_tag_visible=True,
        sym_display_text=sym_text,
        instance_attribs=None,
    )
    if not painted:
        p.setPen(_drag_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(bounds)
    p.end()

    return pm, QPoint(pw // 2, ph // 2)
