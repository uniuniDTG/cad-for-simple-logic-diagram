"""PDF-compatible TEXTSTYLE → FontFace table for Qt canvas rendering.

Builds the same ``RenderContext.fonts`` mapping used by PDF export
(``RenderContext`` + :func:`~logic_cad.core.text.layout_resolver.apply_render_context_fonts_for_pdf_like_ui`)
and caches it per DXF document.
"""

from __future__ import annotations

from typing import Any, Mapping

import ezdxf
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.entities import DXFEntity
from ezdxf.fonts import fonts
from ezdxf.lldxf.validator import make_table_key as _dxf_style_table_key

from logic_cad.core.text.layout_resolver import (
    apply_render_context_fonts_for_pdf_like_ui,
    font_family_preferred_for_named_style,
    resolve_pdf_font_face_for_ui_family_chain,
)

# Global generation counter; bump on invalidate so all per-doc entries go stale.
_cache_generation: int = 0
# id(doc) -> (table copy, generation at build time)
_doc_cache: dict[int, tuple[dict[str, fonts.FontFace], int]] = {}


def build_pdf_like_font_face_table(doc: ezdxf.document.Drawing) -> dict[str, fonts.FontFace]:
    """Build style-key → FontFace map matching PDF export resolution.

    Args:
        doc: DXF drawing backing text styles.

    Returns:
        Mapping from ezdxf TEXTSTYLE table keys to resolved font faces.
    """

    ctx = RenderContext(doc)
    apply_render_context_fonts_for_pdf_like_ui(ctx, doc)
    return dict(ctx.fonts)


def invalidate_pdf_like_font_face_cache(*, doc: Any | None = None) -> None:
    """Drop cached font tables so the next lookup rebuilds from *doc*.

    Args:
        doc: When given, also remove the cache entry for that drawing instance.
    """

    global _cache_generation
    _cache_generation += 1
    if doc is not None:
        _doc_cache.pop(id(doc), None)


def get_pdf_like_font_face_table(doc: ezdxf.document.Drawing) -> Mapping[str, fonts.FontFace]:
    """Return cached PDF-like font faces for *doc*, rebuilding when invalidated.

    Args:
        doc: DXF drawing.

    Returns:
        Read-only mapping of TEXTSTYLE table keys to :class:`~ezdxf.fonts.fonts.FontFace`.
    """

    doc_id = id(doc)
    cached = _doc_cache.get(doc_id)
    if cached is not None and cached[1] == _cache_generation:
        return cached[0]
    table = build_pdf_like_font_face_table(doc)
    _doc_cache[doc_id] = (table, _cache_generation)
    return table


def resolve_outline_font_face_for_entity(
    entity: DXFEntity,
    doc: Any,
    face_table: Mapping[str, fonts.FontFace],
) -> fonts.FontFace | None:
    """Resolve the outline font face for a TEXT/MTEXT/ATTDEF entity like PDF export.

    Lookup order matches PDF: TEXTSTYLE table key, then ``Standard``, then the UI
    family chain via :func:`resolve_pdf_font_face_for_ui_family_chain`.

    Args:
        entity: DXF text-like entity.
        doc: Parent drawing.
        face_table: Pre-built table from :func:`get_pdf_like_font_face_table`.

    Returns:
        Resolved :class:`~ezdxf.fonts.fonts.FontFace`, or ``None`` if unresolved.
    """

    style_name = str(getattr(entity.dxf, "style", "") or "").strip() or "Standard"
    key = _dxf_style_table_key(style_name)
    face = face_table.get(key)
    if face is not None:
        return face
    std_key = _dxf_style_table_key("Standard")
    if key != std_key:
        face = face_table.get(std_key)
        if face is not None:
            return face
    preferred = font_family_preferred_for_named_style(doc, style_name)
    return resolve_pdf_font_face_for_ui_family_chain(preferred, doc=doc)


def resolve_outline_font_face_for_style_name(
    doc: Any,
    style_name: str,
    *,
    face_table: Mapping[str, fonts.FontFace] | None = None,
) -> fonts.FontFace | None:
    """Resolve outline font face from a TEXTSTYLE name (no entity required).

    Args:
        doc: DXF drawing.
        style_name: TEXTSTYLE name (empty → ``Standard``).
        face_table: Optional pre-built table; built on demand when omitted.

    Returns:
        Resolved font face, or ``None``.
    """

    table = face_table if face_table is not None else get_pdf_like_font_face_table(doc)
    name = str(style_name or "").strip() or "Standard"
    key = _dxf_style_table_key(name)
    face = table.get(key)
    if face is not None:
        return face
    std_key = _dxf_style_table_key("Standard")
    if key != std_key:
        face = table.get(std_key)
        if face is not None:
            return face
    preferred = font_family_preferred_for_named_style(doc, name)
    return resolve_pdf_font_face_for_ui_family_chain(preferred, doc=doc)
