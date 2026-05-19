"""Shared text layout utilities."""

from logic_cad.core.text.layout_resolver import (
    NormalizedTextLayout,
    apply_render_context_fonts_for_pdf_like_ui,
    build_single_line_layout,
    font_family_candidates,
    font_family_preferred_for_named_style,
    font_family_preferred_for_style_table_key,
    mtext_attachment_to_text_align,
    normalize_dxf_text_entity,
    normalize_newlines,
    preferred_pdf_font_face,
    preferred_ui_font_family,
    resolve_pdf_font_face_for_ui_family_chain,
    ui_font_family_chain,
)
from logic_cad.core.text.pdf_like_font_faces import (
    build_pdf_like_font_face_table,
    get_pdf_like_font_face_table,
    invalidate_pdf_like_font_face_cache,
    resolve_outline_font_face_for_entity,
    resolve_outline_font_face_for_style_name,
)

__all__ = [
    "NormalizedTextLayout",
    "apply_render_context_fonts_for_pdf_like_ui",
    "build_pdf_like_font_face_table",
    "build_single_line_layout",
    "font_family_candidates",
    "font_family_preferred_for_named_style",
    "font_family_preferred_for_style_table_key",
    "get_pdf_like_font_face_table",
    "invalidate_pdf_like_font_face_cache",
    "mtext_attachment_to_text_align",
    "normalize_dxf_text_entity",
    "normalize_newlines",
    "preferred_pdf_font_face",
    "preferred_ui_font_family",
    "resolve_outline_font_face_for_entity",
    "resolve_outline_font_face_for_style_name",
    "resolve_pdf_font_face_for_ui_family_chain",
    "ui_font_family_chain",
]
