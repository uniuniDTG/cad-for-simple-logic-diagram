"""Logic CAD named TEXTSTYLE for host CAD (BricsCAD) Japanese glyph resolution."""

from __future__ import annotations

from typing import Any, Iterator

from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity

from logic_cad.core.model.constants import TEXT_STYLE_LOGIC_CAD_FONT

# App default when project preferred font is unset: aligns with ``layout_resolver`` MS Gothic first candidate.
_DEFAULT_FONT_FILE = "msgothic.ttc"
_DEFAULT_EXTENDED_FAMILY = "MS Gothic"

# Qt family name (case-insensitive) / normalized keys → (DXF font filename, extended TrueType family hint).
_FAMILY_FONT_TABLE: tuple[tuple[str, ...], tuple[str, str], ...] = (
    (("ms gothic",), (_DEFAULT_FONT_FILE, _DEFAULT_EXTENDED_FAMILY)),
    (("yu gothic ui",), ("YuGothM.ttc", "Yu Gothic UI")),
    (("yu gothic",), ("YuGothR.ttc", "Yu Gothic")),
    (("meiryo",), ("meiryo.ttc", "Meiryo")),
    (("noto sans cjk jp",), ("NotoSansCJKjp-Regular.otf", "Noto Sans CJK JP")),
    (("noto sans jp",), ("NotoSansJP-Regular.otf", "Noto Sans JP")),
    (("ipaexgothic",), ("ipaexg.ttf", "IPAexGothic")),
    (("microsoft yahei", "微软雅黑"), ("msyh.ttc", "Microsoft YaHei")),
    (("arial",), ("arial.ttf", "Arial")),
)


def _normalize_family_key(name: str) -> str:
    """Fold family string for dictionary lookup (spacing/punctuation tolerant)."""

    s = str(name or "").strip().casefold()
    return "".join(ch for ch in s if ch.isalnum())


def font_file_and_extended_family_for_preferred(preferred_family: str | None) -> tuple[str, str]:
    """Map project/UI font family to DXF ``TEXTSTYLE`` font file and extended family hint.

    Args:
        preferred_family: Qt/document preferred family, or ``None`` for app default.

    Returns:
        ``(font_filename, extended_family_name)`` for :meth:`Textstyle.set_extended_font_data`.
    """

    raw = str(preferred_family or "").strip()
    if not raw:
        return (_DEFAULT_FONT_FILE, _DEFAULT_EXTENDED_FAMILY)
    key = _normalize_family_key(raw)
    for aliases, pair in _FAMILY_FONT_TABLE:
        if any(_normalize_family_key(a) == key for a in aliases):
            return pair
    # Unknown dialog entry: pass stem-like token so BricsCAD may still resolve if file exists.
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in (" ", "-", "_")).strip() or _DEFAULT_EXTENDED_FAMILY
    return (_DEFAULT_FONT_FILE, safe[:120])


def merge_logic_cad_text_style_attrib(dxfattribs: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *dxfattribs* with Logic CAD text style applied.

    Args:
        dxfattribs: Partial DXF attributes for TEXT / MTEXT / ATTDEF.

    Returns:
        Attributes dict including ``style=TEXT_STYLE_LOGIC_CAD_FONT``.
    """

    out = dict(dxfattribs)
    out["style"] = TEXT_STYLE_LOGIC_CAD_FONT
    return out


def ensure_logic_cad_font_style(doc: Drawing, *, preferred_family: str | None = None) -> None:
    """Ensure ``TEXT_STYLE_LOGIC_CAD_FONT`` exists and matches project/Japanese defaults.

    DXF carries a single font file per TEXTSTYLE; sync from *preferred_family* when set.

    Args:
        doc: Target drawing.
        preferred_family: Optional Qt family from ``LD_DOC`` (``None`` → MS Gothic file).
    """

    fn, fam = font_file_and_extended_family_for_preferred(preferred_family)
    if TEXT_STYLE_LOGIC_CAD_FONT not in doc.styles:
        doc.styles.add(TEXT_STYLE_LOGIC_CAD_FONT, font=fn)
    ts = doc.styles.get(TEXT_STYLE_LOGIC_CAD_FONT)
    ts.dxf.font = fn
    try:
        ts.set_extended_font_data(fam)
    except (AttributeError, TypeError, ValueError):
        # Older ezdxf / unusual profiles: font filename alone still guides host CAD.
        pass


def set_default_textstyle_header_to_logic_cad(doc: Drawing) -> None:
    """Set ``$TEXTSTYLE`` when our style exists (new TEXT without explicit style use this name)."""

    if TEXT_STYLE_LOGIC_CAD_FONT not in doc.styles:
        return
    try:
        doc.header["$TEXTSTYLE"] = TEXT_STYLE_LOGIC_CAD_FONT
    except (KeyError, AttributeError, TypeError):
        pass


def is_logic_cad_default_host_style_name(style_name: str) -> bool:
    """Return True if *style_name* should be reassigned to ``LOGIC_CAD_FONT`` on save.

    Args:
        style_name: Raw ``entity.dxf.style``.

    Returns:
        True for empty, Standard, or Annotative (case-insensitive).
    """

    s = str(style_name or "").strip().upper()
    return s in {"", "STANDARD", "ANNOTATIVE"}


def iter_text_like_entities(doc: Drawing) -> Iterator[DXFEntity]:
    """Yield TEXT / MTEXT / ATTDEF / ATTRIB entities anywhere in *doc*."""

    for ent in doc.entitydb.values():
        alive = getattr(ent, "is_alive", True)
        if callable(alive):
            alive = alive()
        if not alive:
            continue
        dt = getattr(ent, "dxftype", lambda: "")()
        if dt in {"TEXT", "MTEXT", "ATTDEF", "ATTRIB"}:
            yield ent


def reassign_default_styles_on_text_entities_to_logic_cad_font(doc: Drawing) -> int:
    """Point default-styled text entities at ``LOGIC_CAD_FONT`` for host CAD.

    Custom TEXTSTYLE names from other CAD are preserved.

    Args:
        doc: Drawing about to be saved.

    Returns:
        Count of entities updated.
    """

    if TEXT_STYLE_LOGIC_CAD_FONT not in doc.styles:
        return 0
    n = 0
    for ent in iter_text_like_entities(doc):
        sn = str(getattr(ent.dxf, "style", "") or "").strip()
        if not is_logic_cad_default_host_style_name(sn):
            continue
        ent.dxf.style = TEXT_STYLE_LOGIC_CAD_FONT
        n += 1
    return n


def coerce_entity_style_to_logic_cad_font_if_default(ent: DXFEntity) -> None:
    """After deserialize/restore, assign ``LOGIC_CAD_FONT`` when style was host-default."""

    dt = str(ent.dxftype()).upper()
    if dt not in {"TEXT", "MTEXT", "ATTDEF", "ATTRIB"}:
        return
    doc = getattr(ent, "doc", None)
    if doc is None or TEXT_STYLE_LOGIC_CAD_FONT not in doc.styles:
        return
    if not is_logic_cad_default_host_style_name(str(getattr(ent.dxf, "style", "") or "")):
        return
    ent.dxf.style = TEXT_STYLE_LOGIC_CAD_FONT
