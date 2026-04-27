"""Unified DXF text-layout resolver shared by UI and PDF paths.

This module normalizes TEXT/ATTDEF/ATTRIB/MTEXT attributes into one data
structure so each renderer can focus on drawing, not DXF semantic parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any

from ezdxf.entities import DXFEntity
from ezdxf.fonts import fonts
from ezdxf.lldxf.validator import make_table_key as _dxf_style_table_key

from logic_cad.core.model.document_meta import read_project_preferred_font_family

# Ordered by practical availability on Windows/Japanese environments.
_FONT_FAMILY_CANDIDATES: tuple[str, ...] = (
    "MS Gothic",
    "Yu Gothic UI",
    "Yu Gothic",
    "Meiryo",
    "Noto Sans CJK JP",
    "Noto Sans JP",
    "IPAexGothic",
    "Microsoft YaHei",
    "Arial",
)

_FONT_FILE_STEM_ALIASES: dict[str, str] = {
    "msgothic": "MS Gothic",
    "ms-gothic": "MS Gothic",
    "ms_gothic": "MS Gothic",
    "yugothic": "Yu Gothic",
    "yugothicui": "Yu Gothic UI",
    "meiryo": "Meiryo",
}

_DXF_UNICODE_ESCAPE_RE = re.compile(r"\\U\+([0-9A-Fa-f]{4,8})")


@dataclass(frozen=True)
class NormalizedTextLayout:
    """Renderer-agnostic normalized text parameters.

    Args:
        text: Render text with newline normalized to ``\\n``.
        is_multiline: True for MTEXT-like content.
        insert_x: Entity insert X in DXF millimeters.
        insert_y: Entity insert Y in DXF millimeters.
        anchor_x: Effective anchor X in DXF millimeters.
        anchor_y: Effective anchor Y in DXF millimeters.
        height_mm: Character/cap height in millimeters.
        rotation_deg: DXF rotation in degrees.
        width_factor: Width scale factor for single-line text.
        width_mm: Text box width for multiline text (0 when unspecified).
        halign: Horizontal alignment code compatible with TEXT semantics.
        valign: Vertical alignment code compatible with TEXT semantics.
        render_halign: Effective horizontal alignment for UI rendering.
        render_valign: Effective vertical alignment for UI rendering.
        render_rotation_deg: Effective text rotation for UI rendering.
        render_width_factor: Effective width factor for UI rendering.
        render_fit_length_mm: Target baseline length for FIT/ALIGNED (0 when N/A).
        render_fit_mode: ``none`` | ``fit`` | ``aligned`` for single-line text.
        attachment_point: MTEXT attachment point (1-9, 0 if N/A).
        font_family: Preferred UI font family.
        font_families: Ordered family chain for deterministic Qt resolution.
    """

    text: str
    is_multiline: bool
    insert_x: float
    insert_y: float
    anchor_x: float
    anchor_y: float
    height_mm: float
    rotation_deg: float
    width_factor: float
    width_mm: float
    halign: int
    valign: int
    render_halign: int
    render_valign: int
    render_rotation_deg: float
    render_width_factor: float
    render_fit_length_mm: float
    render_fit_mode: str
    attachment_point: int
    font_family: str
    font_families: tuple[str, ...]


def font_family_candidates() -> tuple[str, ...]:
    """Return preferred font families for Japanese-capable text rendering.

    Returns:
        Ordered fallback list (highest priority first).
    """

    return _FONT_FAMILY_CANDIDATES


def preferred_ui_font_family(style_name: str | None = None) -> str:
    """Resolve a UI font family name from DXF style preference.

    Args:
        style_name: Optional DXF text style name.

    Returns:
        Preferred font family string for Qt rendering.
    """

    s = str(style_name or "").strip()
    if s and s.upper() not in {"STANDARD", "ANNOTATIVE"}:
        return s
    return _FONT_FAMILY_CANDIDATES[0]


def _normalize_family_name(raw: str | None) -> str:
    """Normalize a style/font token into a Qt family-like name.

    Args:
        raw: Family name or font file path.

    Returns:
        Normalized family candidate (empty when unresolved).
    """

    s = str(raw or "").strip().strip('"').strip("'")
    if not s:
        return ""
    token = Path(s).stem.strip() if any(ch in s for ch in ("/", "\\", ".")) else s
    key = token.replace(" ", "").replace("_", "").replace("-", "").lower()
    if key in _FONT_FILE_STEM_ALIASES:
        return _FONT_FILE_STEM_ALIASES[key]
    return token


def ui_font_family_chain(
    preferred_family: str | None = None,
    *,
    project_preferred_font: str | None = None,
) -> tuple[str, ...]:
    """Build deterministic Qt family chain with fallback candidates.

    Resolution order:
    1) Project preferred font (``LD_DOC`` XDATA), when set
    2) DXF style-derived preferred family (if any)
    3) Project candidate list
    4) Generic ``sans-serif`` as last Qt fallback hint

    Args:
        preferred_family: Preferred family or style-derived token.
        project_preferred_font: Optional project setting; when empty/``None``, skipped.

    Returns:
        Ordered, de-duplicated family chain.
    """

    out: list[str] = []
    seen: set[str] = set()

    def _push(name: str) -> None:
        n = _normalize_family_name(name)
        if not n:
            return
        k = n.casefold()
        if k in seen:
            return
        seen.add(k)
        out.append(n)

    pp = str(project_preferred_font or "").strip()
    if pp:
        _push(pp)
    _push(preferred_family or "")
    for fam in _FONT_FAMILY_CANDIDATES:
        _push(fam)
    _push("sans-serif")
    return tuple(out)


def font_family_preferred_for_named_style(doc: Any, style_name: str) -> str:
    """Resolve preferred UI font family from a DXF TEXTSTYLE name.

    Same rules as text entities that reference *style_name* (style table ``font``
    stem/alias first, then :func:`preferred_ui_font_family`).

    Args:
        doc: DXF document providing ``styles``, or ``None``.
        style_name: Raw ``entity.dxf.style`` value.

    Returns:
        Preferred font family string for Qt / PDF resolution.
    """

    style_name = str(style_name or "").strip()
    if doc is None:
        return preferred_ui_font_family(style_name)
    if not style_name:
        return preferred_ui_font_family(None)
    try:
        style = doc.styles.get(style_name)
        if style is None:
            return preferred_ui_font_family(style_name)
        raw_font = str(getattr(style.dxf, "font", "") or "").strip()
        stem = _normalize_family_name(raw_font)
        if stem:
            return stem
    except Exception:
        pass
    return preferred_ui_font_family(style_name)


def _text_style_for_table_key(doc: Any, style_table_key: str) -> Any | None:
    """Return the TEXTSTYLE whose normalized name equals *style_table_key*.

    Args:
        doc: DXF document.
        style_table_key: Normalized key as used by ezdxf ``RenderContext.fonts``.

    Returns:
        Matching style entry, or ``None`` if not found.
    """

    want = _dxf_style_table_key(str(style_table_key or ""))
    for ts in doc.styles:
        if _dxf_style_table_key(str(ts.dxf.name)) == want:
            return ts
    return None


def font_family_preferred_for_style_table_key(doc: Any, style_table_key: str) -> str:
    """Resolve preferred font family for a ``RenderContext.fonts`` map key.

    Args:
        doc: DXF drawing.
        style_table_key: Key ezdxf uses for TEXTSTYLE (see :meth:`RenderContext.add_text_style`).

    Returns:
        Same preferred family string as the Qt UI uses for that text style.
    """

    if doc is None:
        return preferred_ui_font_family(None)
    ts = _text_style_for_table_key(doc, style_table_key)
    if ts is None:
        return preferred_ui_font_family(None)
    raw_font = str(getattr(ts.dxf, "font", "") or "").strip()
    stem = _normalize_family_name(raw_font)
    if stem:
        return stem
    return preferred_ui_font_family(str(ts.dxf.name))


def resolve_pdf_font_face_for_ui_family_chain(
    preferred_family: str,
    *,
    doc: Any | None = None,
) -> fonts.FontFace | None:
    """Pick an outline font face using the same ordered chain as the Qt UI.

    Walks :func:`ui_font_family_chain` and returns the first ``find_best_match`` hit
    with a filename (weight 400, non-italic), matching the PDF pipeline expectations.

    Args:
        preferred_family: Style-derived preferred family (e.g. from
            :func:`font_family_preferred_for_named_style`).
        doc: Optional drawing for project preferred font (``LD_DOC`` XDATA).

    Returns:
        A :class:`~ezdxf.fonts.fonts.FontFace` instance, or ``None`` if unresolved.
    """

    proj = read_project_preferred_font_family(doc) if doc is not None else None
    for fam in ui_font_family_chain(preferred_family, project_preferred_font=proj):
        found = fonts.find_best_match(family=fam, weight=400, italic=False)
        if found is not None and found.filename:
            return found
    return None


def preferred_pdf_font_face() -> fonts.FontFace | None:
    """Resolve a font face using the default UI fallback (no explicit TEXTSTYLE).

    Returns:
        Matched :class:`FontFace` if available; otherwise ``None``.
    """

    return resolve_pdf_font_face_for_ui_family_chain(preferred_ui_font_family(None), doc=None)


def apply_render_context_fonts_for_pdf_like_ui(ctx: Any, doc: Any) -> None:
    """Override ``RenderContext.fonts`` so PDF text matches UI font resolution.

    ezdxf pre-populates font faces from DXF TEXTSTYLE entries. This replaces each
    entry with :func:`resolve_pdf_font_face_for_ui_family_chain` for the preferred
    family implied by that style—the same chain ``normalize_dxf_text_entity`` uses
    for Qt. If the chain resolves to no OS font, the ezdxf-resolved face is left
    unchanged.

    Args:
        ctx: ezdxf :class:`~ezdxf.addons.drawing.properties.RenderContext`.
        doc: DXF :class:`~ezdxf.document.Drawing` backing *ctx*.
    """

    if doc is None:
        return
    for key in list(ctx.fonts.keys()):
        preferred = font_family_preferred_for_style_table_key(doc, str(key))
        face = resolve_pdf_font_face_for_ui_family_chain(preferred, doc=doc)
        if face is not None:
            ctx.fonts[key] = face


def _font_family_from_entity(entity: DXFEntity) -> str:
    """Resolve preferred UI font family from entity style table when possible.

    Args:
        entity: DXF text-like entity.

    Returns:
        Preferred font family for Qt rendering.
    """

    style_name = str(getattr(entity.dxf, "style", "") or "").strip()
    doc = getattr(entity, "doc", None)
    return font_family_preferred_for_named_style(doc, style_name)


def normalize_newlines(text: str) -> str:
    """Normalize DXF MTEXT/TEXT line separators to LF.

    Args:
        text: Raw text content.

    Returns:
        Newline-normalized string.
    """

    t = str(text or "")
    t = _decode_dxf_unicode_escapes(t)
    return t.replace("\\P", "\n").replace("\r\n", "\n").replace("\r", "\n")


def _decode_dxf_unicode_escapes(text: str) -> str:
    """Decode DXF unicode escapes like ``\\U+3042`` to Unicode characters."""

    def _replace(match: re.Match[str]) -> str:
        try:
            cp = int(match.group(1), 16)
            if cp <= 0x10FFFF:
                return chr(cp)
        except Exception:
            pass
        return match.group(0)

    return _DXF_UNICODE_ESCAPE_RE.sub(_replace, str(text or ""))


def mtext_attachment_to_text_align(attachment_point: int) -> tuple[int, int]:
    """Map MTEXT attachment point (1-9) to TEXT-like halign/valign pair.

    Args:
        attachment_point: DXF MTEXT attachment point.

    Returns:
        Tuple ``(halign, valign)`` where ``valign`` uses TEXT conventions:
        top=3, middle=2, bottom=1.
    """

    ap = int(attachment_point or 1)
    if ap < 1 or ap > 9:
        ap = 1
    col = (ap - 1) % 3
    row = (ap - 1) // 3
    halign = (0, 1, 2)[col]
    valign = (3, 2, 1)[row]
    return (halign, valign)


def _placement_anchor_xy(entity: Any) -> tuple[float, float]:
    """Return DXF placement anchor for single-line text-like entities.

    DXF single-line entities use ``insert`` for plain left/baseline text, while
    centered/right/vertical alignments are anchored by ``align_point``. Some
    CAD exports keep both values but only one is semantically active, so we
    resolve anchor explicitly from ``halign``/``valign`` first.

    Args:
        entity: TEXT-like DXF entity.

    Returns:
        Anchor point ``(x, y)`` in DXF units.
    """

    dxf = entity.dxf
    ins = dxf.insert
    insert_xy = (float(ins.x), float(ins.y))
    halign = int(getattr(dxf, "halign", 0) or 0)
    valign = int(getattr(dxf, "valign", 0) or 0)

    if halign == 0 and valign == 0:
        return insert_xy

    align = getattr(dxf, "align_point", None)
    if align is not None and hasattr(align, "x") and hasattr(align, "y"):
        return (float(align.x), float(align.y))

    gp = getattr(entity, "get_placement", None)
    if callable(gp):
        try:
            _align, anchor, _p2 = gp()
            return (float(anchor.x), float(anchor.y))
        except Exception:
            pass
    return insert_xy


def _placement_end_xy(entity: Any) -> tuple[float, float] | None:
    """Return placement secondary point for ALIGNED/FIT when available.

    Args:
        entity: TEXT-like DXF entity.

    Returns:
        Secondary point ``(x, y)`` for placement-based alignments; otherwise ``None``.
    """

    gp = getattr(entity, "get_placement", None)
    if callable(gp):
        try:
            _align, _anchor, p2 = gp()
            if p2 is not None and hasattr(p2, "x") and hasattr(p2, "y"):
                return (float(p2.x), float(p2.y))
        except Exception:
            pass
    align = getattr(entity.dxf, "align_point", None)
    if align is not None and hasattr(align, "x") and hasattr(align, "y"):
        return (float(align.x), float(align.y))
    return None


def _single_line_render_params(
    entity: Any,
    *,
    insert_x: float,
    insert_y: float,
    anchor_x: float,
    anchor_y: float,
    halign: int,
    valign: int,
    rotation_deg: float,
    width_factor: float,
) -> tuple[float, float, int, int, float, float, float, str]:
    """Resolve UI-effective single-line render parameters from DXF alignment.

    Args:
        entity: Source DXF text-like entity.
        insert_x: Raw DXF insert X.
        insert_y: Raw DXF insert Y.
        anchor_x: Raw resolved anchor X.
        anchor_y: Raw resolved anchor Y.
        halign: Raw DXF halign.
        valign: Raw DXF valign.
        rotation_deg: Raw DXF rotation.
        width_factor: Raw DXF width factor.

    Returns:
        Tuple of ``(anchor_x, anchor_y, halign, valign, rotation_deg, width_factor, fit_length_mm, fit_mode)``.
    """

    render_anchor_x = float(anchor_x)
    render_anchor_y = float(anchor_y)
    render_halign = int(halign)
    render_valign = int(valign)
    render_rotation_deg = float(rotation_deg)
    render_width_factor = max(0.1, float(width_factor or 1.0))
    render_fit_length_mm = 0.0
    render_fit_mode = "none"

    if render_halign == 4:
        # DXF MIDDLE is centered on both axes at alignment point.
        render_halign = 1
        render_valign = 2 if render_valign == 0 else render_valign
        align = getattr(entity.dxf, "align_point", None)
        if align is not None and hasattr(align, "x") and hasattr(align, "y"):
            render_anchor_x = float(align.x)
            render_anchor_y = float(align.y)
        return (
            render_anchor_x,
            render_anchor_y,
            render_halign,
            render_valign,
            render_rotation_deg,
            render_width_factor,
            render_fit_length_mm,
            render_fit_mode,
        )

    if render_halign in (3, 5):
        # ALIGNED/FIT use start/end baseline points instead of center/right anchor modes.
        render_anchor_x = float(insert_x)
        render_anchor_y = float(insert_y)
        render_halign = 0
        render_valign = 0
        p2 = _placement_end_xy(entity)
        if p2 is not None:
            dx = float(p2[0]) - render_anchor_x
            dy = float(p2[1]) - render_anchor_y
            length = math.hypot(dx, dy)
            if length > 1e-9:
                render_rotation_deg = math.degrees(math.atan2(dy, dx))
                render_fit_length_mm = length
                render_fit_mode = "aligned" if halign == 3 else "fit"
        return (
            render_anchor_x,
            render_anchor_y,
            render_halign,
            render_valign,
            render_rotation_deg,
            render_width_factor,
            render_fit_length_mm,
            render_fit_mode,
        )

    return (
        render_anchor_x,
        render_anchor_y,
        render_halign,
        render_valign,
        render_rotation_deg,
        render_width_factor,
        render_fit_length_mm,
        render_fit_mode,
    )


def build_single_line_layout(
    *,
    text: str,
    insert_x: float,
    insert_y: float,
    height_mm: float,
    rotation_deg: float = 0.0,
    width_factor: float = 1.0,
    halign: int = 0,
    valign: int = 0,
    font_family: str | None = None,
    doc: Any | None = None,
) -> NormalizedTextLayout:
    """Build normalized layout for app-generated single-line text.

    Args:
        text: Display string.
        insert_x: Insert X in DXF millimeters.
        insert_y: Insert Y in DXF millimeters.
        height_mm: Cap height in millimeters.
        rotation_deg: DXF rotation angle.
        width_factor: Width scaling.
        halign: TEXT horizontal alignment code.
        valign: TEXT vertical alignment code.
        font_family: Optional preferred family.
        doc: Optional DXF drawing for project preferred font resolution.

    Returns:
        Normalized single-line text layout.
    """

    fam = str(font_family or "").strip() or preferred_ui_font_family(None)
    proj = read_project_preferred_font_family(doc) if doc is not None else None
    fam_chain = ui_font_family_chain(fam, project_preferred_font=proj)
    h = max(0.25, float(height_mm or 0.25))
    return NormalizedTextLayout(
        text=normalize_newlines(text),
        is_multiline=False,
        insert_x=float(insert_x),
        insert_y=float(insert_y),
        anchor_x=float(insert_x),
        anchor_y=float(insert_y),
        height_mm=h,
        rotation_deg=float(rotation_deg or 0.0),
        width_factor=max(0.1, float(width_factor or 1.0)),
        width_mm=0.0,
        halign=int(halign or 0),
        valign=int(valign or 0),
        render_halign=int(halign or 0),
        render_valign=int(valign or 0),
        render_rotation_deg=float(rotation_deg or 0.0),
        render_width_factor=max(0.1, float(width_factor or 1.0)),
        render_fit_length_mm=0.0,
        render_fit_mode="none",
        attachment_point=0,
        font_family=fam_chain[0],
        font_families=fam_chain,
    )


def normalize_dxf_text_entity(
    entity: DXFEntity,
    *,
    text_override: str | None = None,
    height_override_mm: float | None = None,
) -> NormalizedTextLayout:
    """Normalize DXF TEXT/ATTDEF/ATTRIB/MTEXT into one layout representation.

    Args:
        entity: Source DXF text-like entity.
        text_override: Optional replacement display text.
        height_override_mm: Optional explicit height in millimeters.

    Returns:
        Normalized text layout.

    Raises:
        ValueError: Entity type is not a supported text kind.
    """

    dt = str(entity.dxftype()).upper()
    fam = _font_family_from_entity(entity)
    edoc = getattr(entity, "doc", None)
    proj = read_project_preferred_font_family(edoc) if edoc is not None else None
    fam_chain = ui_font_family_chain(fam, project_preferred_font=proj)
    if dt == "MTEXT":
        if text_override is not None:
            text = str(text_override)
        else:
            try:
                raw = entity.plain_text()
            except Exception:
                raw = str(getattr(entity, "text", "") or "")
            if isinstance(raw, list):
                text = "\n".join(str(x) for x in raw)
            else:
                text = str(raw)
        ins = entity.dxf.insert
        ap = int(getattr(entity.dxf, "attachment_point", 1) or 1)
        halign, valign = mtext_attachment_to_text_align(ap)
        h = (
            max(0.25, float(height_override_mm))
            if height_override_mm is not None
            else max(0.25, float(getattr(entity.dxf, "char_height", 2.5) or 2.5))
        )
        return NormalizedTextLayout(
            text=normalize_newlines(text),
            is_multiline=True,
            insert_x=float(ins.x),
            insert_y=float(ins.y),
            anchor_x=float(ins.x),
            anchor_y=float(ins.y),
            height_mm=h,
            rotation_deg=float(getattr(entity.dxf, "rotation", 0.0) or 0.0),
            width_factor=1.0,
            width_mm=max(0.0, float(getattr(entity.dxf, "width", 0.0) or 0.0)),
            halign=halign,
            valign=valign,
            render_halign=halign,
            render_valign=valign,
            render_rotation_deg=float(getattr(entity.dxf, "rotation", 0.0) or 0.0),
            render_width_factor=1.0,
            render_fit_length_mm=0.0,
            render_fit_mode="none",
            attachment_point=ap,
            font_family=fam_chain[0],
            font_families=fam_chain,
        )
    if dt in {"TEXT", "ATTDEF", "ATTRIB"}:
        text = str(text_override) if text_override is not None else str(getattr(entity.dxf, "text", "") or "")
        ins = entity.dxf.insert
        insert_x = float(ins.x)
        insert_y = float(ins.y)
        halign = int(getattr(entity.dxf, "halign", 0) or 0)
        valign = int(getattr(entity.dxf, "valign", 0) or 0)
        ax, ay = (insert_x, insert_y) if halign in (3, 5) else _placement_anchor_xy(entity)
        rotation_deg = float(getattr(entity.dxf, "rotation", 0.0) or 0.0)
        width_factor = max(0.1, float(getattr(entity.dxf, "width", 1.0) or 1.0))
        (
            render_anchor_x,
            render_anchor_y,
            render_halign,
            render_valign,
            render_rotation_deg,
            render_width_factor,
            render_fit_length_mm,
            render_fit_mode,
        ) = _single_line_render_params(
            entity,
            insert_x=insert_x,
            insert_y=insert_y,
            anchor_x=ax,
            anchor_y=ay,
            halign=halign,
            valign=valign,
            rotation_deg=rotation_deg,
            width_factor=width_factor,
        )
        h = (
            max(0.25, float(height_override_mm))
            if height_override_mm is not None
            else max(0.25, float(getattr(entity.dxf, "height", 2.5) or 2.5))
        )
        return NormalizedTextLayout(
            text=normalize_newlines(text),
            is_multiline=False,
            insert_x=insert_x,
            insert_y=insert_y,
            anchor_x=render_anchor_x,
            anchor_y=render_anchor_y,
            height_mm=h,
            rotation_deg=rotation_deg,
            width_factor=width_factor,
            width_mm=0.0,
            halign=halign,
            valign=valign,
            render_halign=render_halign,
            render_valign=render_valign,
            render_rotation_deg=render_rotation_deg,
            render_width_factor=render_width_factor,
            render_fit_length_mm=render_fit_length_mm,
            render_fit_mode=render_fit_mode,
            attachment_point=0,
            font_family=fam_chain[0],
            font_families=fam_chain,
        )
    raise ValueError(f"Unsupported text entity type: {dt}")
