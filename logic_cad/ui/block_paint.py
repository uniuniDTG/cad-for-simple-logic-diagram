"""Render DXF block definition geometry in QPainter (item-local, DXF Y up → scene Y down)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QTransform,
)

if TYPE_CHECKING:
    from ezdxf.document import Drawing

from logic_cad.core.attrib_tags import is_frame_attdef_tag, is_supported_attdef_tag
from logic_cad.core.model.constants import LAYER_CONTENTS_AREA
from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity
from logic_cad.ui.dxf_display_color import entity_effective_linetype, entity_stroke_qcolor
from logic_cad.ui.items.wire_item import apply_dxf_linetype_to_pen


def _local_pt(x: float, y: float, sx: float, sy: float) -> QPointF:
    return QPointF(x * sx, -y * sy)


def glyph_upright_extra_deg(insert_rotation_deg: float) -> float:
    """When INSERT is 180°, return +180 to add to text rotation so glyphs stay readable on screen."""
    r = float(insert_rotation_deg) % 360.0
    if r < 0:
        r += 360.0
    if abs(r - 180.0) <= 0.5:
        return 180.0
    return 0.0


# Reference point size for outline text path (actual height → cap_mm via uniform scale).
_ATTDEF_TEXT_REF_PT = 10.0


def _text_reference_height(path_height: float, line_height: float, cap_height: float) -> float:
    """Return a stable source height for mm scaling.

    Prefer glyph/path height for visual parity with CAD/PDF.
    Fall back to line box only when outline bounds are suspiciously tiny
    (observed on some Qt/font combinations).
    """

    ph = max(float(path_height), 0.0)
    lh = max(float(line_height), 0.0)
    ch = max(float(cap_height), 0.0)
    if lh > 1e-6 and ph < 0.35 * lh:
        return max(lh, 1e-6)
    return max(ph, ch, 1e-6)


def _instance_attrib_entry(
    instance_attribs: dict[str, tuple[str, bool]], tag: str
) -> tuple[str, bool] | None:
    u = str(tag).upper()
    for k, v in instance_attribs.items():
        if str(k).upper() == u:
            return v
    return None


def _effective_halign(halign: int, glyph_extra_deg: float, rot_deg: float) -> int:
    """Return the effective halign after accounting for a 180° total rotation.

    When the combined glyph rotation is approximately 180°, the painter's X axis is
    reversed, so the alignment offset ``dx`` is applied in the opposite direction.
    Swapping left (0) ↔ right (2) compensates for this, keeping the text anchor
    semantics consistent with 0° rotation.  Center (1) is symmetric and unchanged.
    """
    total = (glyph_extra_deg + rot_deg) % 360.0
    if total < 0.0:
        total += 360.0
    if abs(total - 180.0) <= 0.5:
        if halign == 0:
            return 2
        if halign == 2:
            return 0
    return halign


def _effective_valign(valign: int, glyph_extra_deg: float, rot_deg: float) -> int:
    """Return the effective valign after accounting for a 180° total rotation.

    When the combined glyph rotation is approximately 180°, the painter's Y axis is
    reversed, so the alignment offset ``dy`` is applied in the opposite direction.
    Swapping baseline (0) ↔ top (3) compensates for this, keeping the text anchor
    semantics consistent with 0° rotation.  Middle (2) is symmetric and unchanged.
    """
    total = (glyph_extra_deg + rot_deg) % 360.0
    if total < 0.0:
        total += 360.0
    if abs(total - 180.0) <= 0.5:
        if valign == 0:
            return 3
        if valign == 3:
            return 0
    return valign


def paint_text_path_mm(
    painter: QPainter,
    text: str,
    cap_mm: float,
    pos: QPointF,
    *,
    rot_deg: float = 0.0,
    glyph_extra_deg: float = 0.0,
    halign: int = 0,
    valign: int = 0,
    width_fac: float = 1.0,
    fit_length_mm: float = 0.0,
    fit_mode: str = "none",
    fill: QColor | None = None,
    font_family: str = "Arial",
    font_families: tuple[str, ...] | None = None,
) -> None:
    """Draw text with outline path scaled so bounding height = cap_mm (item / scene mm)."""
    if cap_mm < 1e-12 or not (text or "").strip():
        return
    col = fill if fill is not None else QColor(220, 220, 220)
    font = QFont()
    if font_families:
        font.setFamilies(list(font_families))
    else:
        font.setFamily(font_family)
    stretch = int(max(10, min(400, round(100 * width_fac))))
    font.setStretch(stretch)
    font.setPointSizeF(_ATTDEF_TEXT_REF_PT)
    fm = QFontMetricsF(font)
    adv = float(fm.horizontalAdvance(text))
    path = QPainterPath()
    path.addText(0.0, 0.0, font, text)
    br = path.boundingRect()
    h0 = _text_reference_height(float(br.height()), float(fm.height()), float(fm.capHeight()))
    s = cap_mm / h0
    top = float(br.top())
    bottom = float(br.bottom())
    # Normalize DXF special alignments to render-time primitives.
    if halign == 4:
        halign = 1
        valign = 2 if valign == 0 else valign
    elif halign in (3, 5):
        halign = 0
        valign = 0

    stretch_x = 1.0
    stretch_y = 1.0
    if fit_length_mm > 1e-6:
        nominal_w = s * adv
        if nominal_w > 1e-12:
            ratio = max(1e-6, fit_length_mm / nominal_w)
            stretch_x = ratio
            if str(fit_mode).lower() == "aligned":
                stretch_y = ratio

    eff_halign = _effective_halign(halign, glyph_extra_deg, rot_deg)
    if eff_halign == 1:
        dx = -stretch_x * s * adv / 2.0
    elif eff_halign == 2:
        dx = -stretch_x * s * adv
    else:
        dx = 0.0
    eff_valign = _effective_valign(valign, glyph_extra_deg, rot_deg)
    if eff_valign == 2:
        dy = -0.5 * s * (top + bottom)
    elif eff_valign == 3:
        dy = -s * top
    elif eff_valign == 1:
        dy = -s * bottom
    else:
        dy = 0.0
    painter.save()
    painter.translate(pos)
    painter.rotate(glyph_extra_deg + rot_deg)
    painter.translate(dx, dy)
    painter.scale(s * stretch_x, s * stretch_y)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(col))
    painter.drawPath(path)
    painter.restore()


def text_path_bounds_item_local(
    text: str,
    cap_mm: float,
    pos: QPointF,
    *,
    rot_deg: float = 0.0,
    glyph_extra_deg: float = 0.0,
    halign: int = 0,
    valign: int = 0,
    width_fac: float = 1.0,
    fit_length_mm: float = 0.0,
    fit_mode: str = "none",
    font_family: str = "Arial",
    font_families: tuple[str, ...] | None = None,
) -> QRectF | None:
    """Axis-aligned bounds of ``paint_text_path_mm`` output in item-local coords (mm)."""
    if cap_mm < 1e-12 or not (text or "").strip():
        return None
    font = QFont()
    if font_families:
        font.setFamilies(list(font_families))
    else:
        font.setFamily(font_family)
    stretch = int(max(10, min(400, round(100 * width_fac))))
    font.setStretch(stretch)
    font.setPointSizeF(_ATTDEF_TEXT_REF_PT)
    fm = QFontMetricsF(font)
    adv = float(fm.horizontalAdvance(text))
    path = QPainterPath()
    path.addText(0.0, 0.0, font, text)
    br = path.boundingRect()
    h0 = _text_reference_height(float(br.height()), float(fm.height()), float(fm.capHeight()))
    s = cap_mm / h0
    top = float(br.top())
    bottom = float(br.bottom())
    if halign == 4:
        halign = 1
        valign = 2 if valign == 0 else valign
    elif halign in (3, 5):
        halign = 0
        valign = 0

    stretch_x = 1.0
    stretch_y = 1.0
    if fit_length_mm > 1e-6:
        nominal_w = s * adv
        if nominal_w > 1e-12:
            ratio = max(1e-6, fit_length_mm / nominal_w)
            stretch_x = ratio
            if str(fit_mode).lower() == "aligned":
                stretch_y = ratio

    eff_halign = _effective_halign(halign, glyph_extra_deg, rot_deg)
    if eff_halign == 1:
        dx = -stretch_x * s * adv / 2.0
    elif eff_halign == 2:
        dx = -stretch_x * s * adv
    else:
        dx = 0.0
    eff_valign = _effective_valign(valign, glyph_extra_deg, rot_deg)
    if eff_valign == 2:
        dy = -0.5 * s * (top + bottom)
    elif eff_valign == 3:
        dy = -s * top
    elif eff_valign == 1:
        dy = -s * bottom
    else:
        dy = 0.0
    xf = QTransform()
    xf.translate(pos.x(), pos.y())
    xf.rotate(glyph_extra_deg + rot_deg)
    xf.translate(dx, dy)
    xf.scale(s * stretch_x, s * stretch_y)
    r = path.boundingRect()
    corners = (
        QPointF(r.left(), r.top()),
        QPointF(r.right(), r.top()),
        QPointF(r.left(), r.bottom()),
        QPointF(r.right(), r.bottom()),
    )
    mapped = [xf.map(c) for c in corners]
    xs = [p.x() for p in mapped]
    ys = [p.y() for p in mapped]
    return QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))


def _mtext_anchor_offsets(bounds: QRectF, halign: int, valign: int) -> tuple[float, float]:
    """Return translation offsets that place the requested anchor at (0, 0)."""

    if halign == 1:
        dx = -0.5 * (bounds.left() + bounds.right())
    elif halign in (2, 3, 4):
        dx = -bounds.right()
    else:
        dx = -bounds.left()

    if valign == 2:
        dy = -0.5 * (bounds.top() + bounds.bottom())
    elif valign == 1:
        dy = -bounds.bottom()
    else:
        dy = -bounds.top()
    return (dx, dy)


def _wrap_text_line_to_width_mm(
    line: str,
    *,
    cap_mm: float,
    width_mm: float,
    width_fac: float,
    font_family: str,
    font_families: tuple[str, ...] | None,
) -> list[str]:
    """Greedy-wrap one line to fit target width (mm) using current text metrics."""

    s = str(line or "")
    if not s.strip():
        return [""]

    def fits(t: str) -> bool:
        br = text_path_bounds_item_local(
            t,
            cap_mm,
            QPointF(0.0, 0.0),
            halign=0,
            valign=3,
            width_fac=width_fac,
            font_family=font_family,
            font_families=font_families,
        )
        return br is None or br.width() <= width_mm + 1e-6

    if fits(s):
        return [s]

    # Keep explicit spaces in visual flow.
    words = s.split(" ")
    out: list[str] = []
    cur = ""
    for w in words:
        cand = w if not cur else f"{cur} {w}"
        if fits(cand):
            cur = cand
            continue
        if cur:
            out.append(cur)
            cur = w
            if fits(cur):
                continue
        # Fallback: character wrap for a single long token.
        token = w
        chunk = ""
        for ch in token:
            cand2 = f"{chunk}{ch}"
            if not chunk or fits(cand2):
                chunk = cand2
                continue
            out.append(chunk)
            chunk = ch
        cur = chunk
    if cur:
        out.append(cur)
    return out if out else [s]


def mtext_wrapped_lines_mm(
    text: str,
    *,
    cap_mm: float,
    width_mm: float = 0.0,
    width_fac: float = 1.0,
    font_family: str = "Arial",
    font_families: tuple[str, ...] | None = None,
) -> list[str]:
    """Return wrapped multiline content for MTEXT-like path rendering."""

    src = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = src.split("\n") if src else [""]
    if width_mm <= 1e-6:
        return raw_lines
    out: list[str] = []
    for ln in raw_lines:
        out.extend(
            _wrap_text_line_to_width_mm(
                ln,
                cap_mm=cap_mm,
                width_mm=width_mm,
                width_fac=width_fac,
                font_family=font_family,
                font_families=font_families,
            )
        )
    return out


def mtext_path_bounds_item_local(
    text: str,
    cap_mm: float,
    *,
    width_mm: float = 0.0,
    line_gap_ratio: float = 0.2,
    halign: int = 0,
    valign: int = 3,
    width_fac: float = 1.0,
    font_family: str = "Arial",
    font_families: tuple[str, ...] | None = None,
) -> QRectF | None:
    """Bounds of multiline path text with attachment-style anchoring."""

    if cap_mm < 1e-12:
        return None
    lines = mtext_wrapped_lines_mm(
        text,
        cap_mm=cap_mm,
        width_mm=width_mm,
        width_fac=width_fac,
        font_family=font_family,
        font_families=font_families,
    )
    if not lines:
        return None

    step = max(cap_mm * (1.0 + max(0.0, line_gap_ratio)), cap_mm)
    body: QRectF | None = None
    for i, ln in enumerate(lines):
        r = text_path_bounds_item_local(
            ln,
            cap_mm,
            QPointF(0.0, i * step),
            halign=0,
            valign=3,
            width_fac=width_fac,
            font_family=font_family,
            font_families=font_families,
        )
        if r is None or r.isEmpty():
            continue
        body = r if body is None else body.united(r)
    if body is None:
        return None
    dx, dy = _mtext_anchor_offsets(body, halign, valign)
    return body.translated(dx, dy)


def paint_mtext_path_mm(
    painter: QPainter,
    text: str,
    cap_mm: float,
    anchor_pos: QPointF,
    *,
    width_mm: float = 0.0,
    line_gap_ratio: float = 0.2,
    rot_deg: float = 0.0,
    halign: int = 0,
    valign: int = 3,
    width_fac: float = 1.0,
    fill: QColor | None = None,
    font_family: str = "Arial",
    font_families: tuple[str, ...] | None = None,
) -> None:
    """Draw multiline path text anchored like MTEXT in item/scene millimeters."""

    if cap_mm < 1e-12:
        return
    lines = mtext_wrapped_lines_mm(
        text,
        cap_mm=cap_mm,
        width_mm=width_mm,
        width_fac=width_fac,
        font_family=font_family,
        font_families=font_families,
    )
    if not lines:
        return
    body = mtext_path_bounds_item_local(
        text,
        cap_mm,
        width_mm=width_mm,
        line_gap_ratio=line_gap_ratio,
        halign=0,
        valign=3,
        width_fac=width_fac,
        font_family=font_family,
        font_families=font_families,
    )
    if body is None:
        return
    dx, dy = _mtext_anchor_offsets(body, halign, valign)
    step = max(cap_mm * (1.0 + max(0.0, line_gap_ratio)), cap_mm)
    painter.save()
    painter.translate(anchor_pos)
    painter.rotate(rot_deg)
    for i, ln in enumerate(lines):
        paint_text_path_mm(
            painter,
            ln,
            cap_mm,
            QPointF(dx, dy + i * step),
            halign=0,
            valign=3,
            width_fac=width_fac,
            fill=fill,
            font_family=font_family,
            font_families=font_families,
        )
    painter.restore()


def supported_attdefs_bounds_item_local(
    doc: Drawing,
    block_name: str,
    scale_x: float,
    scale_y: float,
    *,
    glyph_extra_deg: float = 0.0,
    sym_tag_visible: bool = True,
    sym_display_text: str = "",
    instance_attribs: dict[str, tuple[str, bool]] | None = None,
) -> QRectF | None:
    """Union of ATTDEF text bounds using instance strings (same rules as ``paint_block_attdefs``)."""
    if block_name not in doc.blocks:
        return None
    blk = doc.blocks.get(block_name)
    inst = instance_attribs or {}
    out: QRectF | None = None
    for ent in blk:
        if ent.dxftype() != "ATTDEF":
            continue
        if str(ent.dxf.layer).startswith("LD_PORT_"):
            continue
        tag = str(ent.dxf.tag)
        if not (is_supported_attdef_tag(tag) or is_frame_attdef_tag(tag)):
            continue
        tag_u = tag.upper()

        if tag_u == "SYM":
            if not sym_tag_visible:
                continue
            t = sym_display_text.strip() if sym_display_text else ""
            if not t and tag in inst:
                t = str(inst[tag][0] or "")
            if not t:
                t = str(ent.dxf.text or "")
        else:
            if tag in inst:
                t = str(inst[tag][0] or "")
                inv = bool(inst[tag][1])
            else:
                t = str(ent.dxf.text or "")
                inv = bool(getattr(ent.dxf, "invisible", 0))
            if inv:
                continue

        if not t.strip():
            continue

        layout = normalize_dxf_text_entity(ent, text_override=t)
        pos = _local_pt(layout.anchor_x, layout.anchor_y, scale_x, scale_y)
        sf = min(abs(scale_x), abs(scale_y)) if scale_x and scale_y else 1.0
        cap_mm = float(layout.height_mm) * sf

        br = text_path_bounds_item_local(
            layout.text,
            cap_mm,
            pos,
            rot_deg=-layout.render_rotation_deg,
            glyph_extra_deg=glyph_extra_deg,
            halign=layout.render_halign,
            valign=layout.render_valign,
            width_fac=layout.render_width_factor,
            fit_length_mm=layout.render_fit_length_mm,
            fit_mode=layout.render_fit_mode,
            font_family=layout.font_family,
            font_families=layout.font_families,
        )
        if br is None or br.isEmpty():
            continue
        out = br if out is None else out.united(br)
    return out


def block_has_sym_attdef(doc: Drawing, block_name: str) -> bool:
    if block_name not in doc.blocks:
        return False
    for ent in doc.blocks.get(block_name):
        if ent.dxftype() == "ATTDEF" and str(ent.dxf.tag).upper() == "SYM":
            return True
    return False


def block_scaled_bounds(
    doc: Drawing,
    block_name: str,
    sx: float,
    sy: float,
    pad: float = 0.6,
) -> QRectF | None:
    """Bounding rect in item-local coords (same convention as paint routines)."""
    if block_name not in doc.blocks:
        return None
    blk = doc.blocks.get(block_name)
    geoms = [e for e in blk if str(e.dxf.layer) != LAYER_CONTENTS_AREA]
    if not geoms:
        return None
    try:
        from ezdxf import bbox

        e = bbox.extents(geoms)
    except Exception:
        return None
    if e is None:
        return None
    s = e.size
    if abs(float(s.x)) < 1e-12 and abs(float(s.y)) < 1e-12:
        return None
    emin, emax = e.extmin, e.extmax
    corners = [
        (float(emin.x) * sx, -float(emin.y) * sy),
        (float(emin.x) * sx, -float(emax.y) * sy),
        (float(emax.x) * sx, -float(emin.y) * sy),
        (float(emax.x) * sx, -float(emax.y) * sy),
    ]
    xs = [c[0] for c in corners]
    ys = [c[1] for c in corners]
    return QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)


def block_scaled_bounds_with_instance(
    doc: Drawing,
    block_name: str,
    sx: float,
    sy: float,
    *,
    glyph_extra_deg: float = 0.0,
    instance_attribs: dict[str, tuple[str, bool]] | None = None,
    sym_display_text: str = "",
    sym_tag_visible: bool = True,
    pad: float = 0.6,
) -> QRectF | None:
    """Like ``block_scaled_bounds`` but ATTDEF size follows instance text (preview-consistent)."""
    if block_name not in doc.blocks:
        return None
    blk = doc.blocks.get(block_name)
    try:
        from ezdxf import bbox as dxf_bbox

        non_attdef = [
            e for e in blk if e.dxftype() != "ATTDEF" and str(e.dxf.layer) != LAYER_CONTENTS_AREA
        ]
        e = dxf_bbox.extents(non_attdef) if non_attdef else None
    except Exception:
        e = None

    geo_rect: QRectF | None = None
    if e is not None and getattr(e, "has_data", False):
        sz = e.size
        if abs(float(sz.x)) >= 1e-12 or abs(float(sz.y)) >= 1e-12:
            emin, emax = e.extmin, e.extmax
            corners = [
                (float(emin.x) * sx, -float(emin.y) * sy),
                (float(emin.x) * sx, -float(emax.y) * sy),
                (float(emax.x) * sx, -float(emin.y) * sy),
                (float(emax.x) * sx, -float(emax.y) * sy),
            ]
            xs = [c[0] for c in corners]
            ys = [c[1] for c in corners]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            if w < 1e-9:
                w = 1e-6
            if h < 1e-9:
                h = 1e-6
            geo_rect = QRectF(min(xs), min(ys), w, h)

    text_rect = supported_attdefs_bounds_item_local(
        doc,
        block_name,
        sx,
        sy,
        glyph_extra_deg=glyph_extra_deg,
        sym_tag_visible=sym_tag_visible,
        sym_display_text=sym_display_text,
        instance_attribs=instance_attribs,
    )

    combined: QRectF | None = None
    if geo_rect is not None and not geo_rect.isEmpty():
        combined = geo_rect
    if text_rect is not None and not text_rect.isEmpty():
        combined = text_rect if combined is None else combined.united(text_rect)

    if combined is None or combined.isEmpty():
        return block_scaled_bounds(doc, block_name, sx, sy, pad=pad)

    return QRectF(
        combined.left() - pad,
        combined.top() - pad,
        combined.width() + 2 * pad,
        combined.height() + 2 * pad,
    )


def _dxf_aci_color(idx: int) -> QColor:
    """Approximate ACI → QColor (dark UI-friendly)."""
    if idx == 0 or idx == 256:
        return QColor(210, 210, 215, 160)
    if idx == 1:
        return QColor(220, 80, 80, 140)
    if idx == 3:
        return QColor(100, 200, 120, 140)
    if idx == 5:
        return QColor(120, 160, 240, 140)
    return QColor(200, 200, 210, 120)


def paint_block_hatches(
    painter: QPainter,
    doc: Drawing,
    block_name: str,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    flatten: float = 0.35,
) -> bool:
    from ezdxf.path import make_path

    if block_name not in doc.blocks:
        return False
    blk = doc.blocks.get(block_name)
    drawn = False
    for ent in blk:
        if ent.dxftype() != "HATCH":
            continue
        if str(ent.dxf.layer) == LAYER_CONTENTS_AREA:
            continue
        if str(ent.dxf.layer).startswith("LD_PORT_"):
            continue
        try:
            path = make_path(ent)
        except Exception:
            continue
        subs = list(path.sub_paths()) if path.has_sub_paths else [path]
        col = _dxf_aci_color(int(getattr(ent.dxf, "color", 0) or 0))
        painter.save()
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(col))
        for sub in subs:
            if len(sub) == 0:
                continue
            try:
                pts = list(sub.flattening(flatten))
            except Exception:
                continue
            if len(pts) < 3:
                continue
            poly = QPolygonF([_local_pt(float(p.x), float(p.y), scale_x, scale_y) for p in pts])
            painter.drawPolygon(poly)
            drawn = True
        painter.restore()
    return drawn


def paint_block_strokes(
    painter: QPainter,
    doc: Drawing,
    block_name: str,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    flatten: float = 0.35,
    stroke_color_override: QColor | None = None,
) -> bool:
    from ezdxf.path import make_path

    if block_name not in doc.blocks:
        return False
    blk = doc.blocks.get(block_name)
    painter.setBrush(Qt.NoBrush)
    drawn = False
    override = stroke_color_override

    for ent in blk:
        layer = str(ent.dxf.layer)
        if layer == LAYER_CONTENTS_AREA:
            continue
        if layer.startswith("LD_PORT_"):
            continue
        dt = ent.dxftype()
        if dt in ("POINT", "ATTDEF", "ATTRIB", "INSERT", "SEQEND", "HATCH", "TEXT", "MTEXT"):
            continue
        try:
            path = make_path(ent)
        except Exception:
            continue
        stroke_q = override if override is not None else entity_stroke_qcolor(doc, ent)
        lt_resolved = entity_effective_linetype(doc, ent)
        if path.has_sub_paths:
            subs = list(path.sub_paths())
        else:
            subs = [path]
        for sub in subs:
            if len(sub) == 0:
                continue
            try:
                pts = list(sub.flattening(flatten))
            except Exception:
                continue
            if len(pts) < 2:
                continue
            geom = QPainterPath()
            p0 = _local_pt(float(pts[0].x), float(pts[0].y), scale_x, scale_y)
            geom.moveTo(p0)
            for pi in pts[1:]:
                geom.lineTo(_local_pt(float(pi.x), float(pi.y), scale_x, scale_y))
            painter.save()
            pen = QPen(stroke_q, 0)
            pen.setCosmetic(True)
            apply_dxf_linetype_to_pen(pen, lt_resolved)
            painter.setPen(pen)
            painter.drawPath(geom)
            painter.restore()
            drawn = True
    return drawn


def paint_block_text_entities(
    painter: QPainter,
    doc: Drawing,
    block_name: str,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
) -> bool:
    """Draw TEXT/MTEXT entities in block definitions on all visible layers."""
    if block_name not in doc.blocks:
        return False
    blk = doc.blocks.get(block_name)
    pen = QPen(QColor(220, 220, 220))
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    drawn = False
    for ent in blk:
        dt = str(ent.dxftype()).upper()
        if dt not in {"TEXT", "MTEXT"}:
            continue
        layer = str(getattr(ent.dxf, "layer", ""))
        if layer == LAYER_CONTENTS_AREA or layer.startswith("LD_PORT_"):
            continue
        layout = normalize_dxf_text_entity(ent)
        if not layout.text.strip():
            continue
        pos = _local_pt(layout.anchor_x, layout.anchor_y, scale_x, scale_y)
        sf = min(abs(scale_x), abs(scale_y)) if scale_x and scale_y else 1.0
        cap_mm = float(layout.height_mm) * sf
        if layout.is_multiline:
            paint_mtext_path_mm(
                painter,
                layout.text,
                cap_mm,
                pos,
                width_mm=float(layout.width_mm) * sf,
                rot_deg=-layout.render_rotation_deg,
                halign=layout.render_halign,
                valign=layout.render_valign,
                width_fac=layout.render_width_factor,
                fill=pen.color(),
                font_family=layout.font_family,
                font_families=layout.font_families,
            )
        else:
            paint_text_path_mm(
                painter,
                layout.text,
                cap_mm,
                pos,
                rot_deg=-layout.render_rotation_deg,
                halign=layout.render_halign,
                valign=layout.render_valign,
                width_fac=layout.render_width_factor,
                fit_length_mm=layout.render_fit_length_mm,
                fit_mode=layout.render_fit_mode,
                fill=pen.color(),
                font_family=layout.font_family,
                font_families=layout.font_families,
            )
        drawn = True
    return drawn


def paint_block_attdefs(
    painter: QPainter,
    doc: Drawing,
    block_name: str,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    glyph_extra_deg: float = 0.0,
    sym_tag_visible: bool = True,
    sym_display_text: str = "",
    instance_attribs: dict[str, tuple[str, bool]] | None = None,
    sym_height_mm: float | None = None,
) -> bool:
    """Draw ATTDEFs using **instance** ATTRIB text when available (SYM from 配置/ref).

    Args:
        sym_height_mm: When set, overrides block ATTDEF height for SYM text only (drawing mm).
    """
    if block_name not in doc.blocks:
        return False
    blk = doc.blocks.get(block_name)
    inst = instance_attribs or {}
    drawn = False
    pen = QPen(QColor(220, 220, 220))
    pen.setCosmetic(True)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)

    for ent in blk:
        if ent.dxftype() != "ATTDEF":
            continue
        if str(ent.dxf.layer).startswith("LD_PORT_"):
            continue
        tag = str(ent.dxf.tag)
        if not (is_supported_attdef_tag(tag) or is_frame_attdef_tag(tag)):
            continue
        tag_u = tag.upper()

        if tag_u == "SYM":
            if not sym_tag_visible:
                continue
            text = sym_display_text.strip() if sym_display_text else ""
            sym_pair = _instance_attrib_entry(inst, "SYM")
            if not text and sym_pair is not None:
                text = str(sym_pair[0] or "")
            if not text:
                text = str(ent.dxf.text or "")
        else:
            inst_pair = _instance_attrib_entry(inst, tag)
            if inst_pair is not None:
                text = str(inst_pair[0] or "")
                inv = bool(inst_pair[1])
            else:
                text = str(ent.dxf.text or "")
                inv = bool(getattr(ent.dxf, "invisible", 0))
            if inv:
                continue

        if not text.strip():
            continue

        h_override = None
        if tag_u == "SYM" and sym_height_mm is not None and float(sym_height_mm) > 0:
            h_override = max(0.25, float(sym_height_mm))
        layout = normalize_dxf_text_entity(ent, text_override=text, height_override_mm=h_override)
        pos = _local_pt(layout.anchor_x, layout.anchor_y, scale_x, scale_y)

        sf = min(abs(scale_x), abs(scale_y)) if scale_x and scale_y else 1.0
        cap_mm = float(layout.height_mm) * sf

        paint_text_path_mm(
            painter,
            layout.text,
            cap_mm,
            pos,
            rot_deg=-layout.render_rotation_deg,
            glyph_extra_deg=glyph_extra_deg,
            halign=layout.render_halign,
            valign=layout.render_valign,
            width_fac=layout.render_width_factor,
            fit_length_mm=layout.render_fit_length_mm,
            fit_mode=layout.render_fit_mode,
            fill=pen.color(),
            font_family=layout.font_family,
            font_families=layout.font_families,
        )
        drawn = True
    return drawn


def paint_block_definition(
    painter: QPainter,
    doc: Drawing,
    block_name: str,
    *,
    scale_x: float = 1.0,
    scale_y: float = 1.0,
    flatten: float = 0.35,
    glyph_extra_deg: float = 0.0,
    sym_tag_visible: bool = True,
    sym_display_text: str = "",
    instance_attribs: dict[str, tuple[str, bool]] | None = None,
    sym_height_mm: float | None = None,
    stroke_color_override: QColor | None = None,
) -> bool:
    """Hatches + strokes + TEXT/MTEXT + ATTDEF. Returns True if any geometry/text drawn."""
    a = paint_block_hatches(painter, doc, block_name, scale_x=scale_x, scale_y=scale_y, flatten=flatten)
    b = paint_block_strokes(
        painter,
        doc,
        block_name,
        scale_x=scale_x,
        scale_y=scale_y,
        flatten=flatten,
        stroke_color_override=stroke_color_override,
    )
    c = paint_block_text_entities(painter, doc, block_name, scale_x=scale_x, scale_y=scale_y)
    d = paint_block_attdefs(
        painter,
        doc,
        block_name,
        scale_x=scale_x,
        scale_y=scale_y,
        glyph_extra_deg=glyph_extra_deg,
        sym_tag_visible=sym_tag_visible,
        sym_display_text=sym_display_text,
        instance_attribs=instance_attribs,
        sym_height_mm=sym_height_mm,
    )
    return a or b or c or d
