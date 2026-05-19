"""Tests for unified DXF text layout normalization."""

from __future__ import annotations

from unittest.mock import patch

import ezdxf
from ezdxf.addons.drawing.properties import RenderContext
from ezdxf.enums import TextEntityAlignment
from ezdxf.fonts import fonts
from ezdxf.lldxf.validator import make_table_key
from PySide6.QtCore import QPointF
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from logic_cad.core.text.layout_resolver import (
    apply_render_context_fonts_for_pdf_like_ui,
    build_single_line_layout,
    decode_dxf_unicode_escapes,
    font_family_candidates,
    font_family_preferred_for_style_table_key,
    normalize_dxf_text_entity,
    preferred_ui_font_family,
    ui_font_family_chain,
)
from logic_cad.core.text.pdf_like_font_faces import (
    build_pdf_like_font_face_table,
    get_pdf_like_font_face_table,
    invalidate_pdf_like_font_face_cache,
)
from logic_cad.ui.block_paint import (
    _qfont_from_font_face,
    mtext_path_bounds_item_local,
    text_path_bounds_item_local,
)


def _new_doc() -> ezdxf.document.Drawing:
    """Create a tiny DXF document for text-layout tests.

    Returns:
        Fresh R2010 drawing.
    """

    return ezdxf.new("R2010", setup=["styles"], units=4)


def _ensure_qt_app() -> QApplication:
    """Return an active QApplication for font-metrics based tests."""

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_normalize_text_resolves_alignment_anchor_via_placement() -> None:
    """TEXT anchor should follow DXF placement point when explicitly set.

    Returns:
        None
    """

    doc = _new_doc()
    msp = doc.modelspace()
    ent = msp.add_text("abc", height=3.5, dxfattribs={"insert": (10.0, 20.0)})
    ent.set_placement((30.0, 40.0), align=TextEntityAlignment.MIDDLE_CENTER)

    layout = normalize_dxf_text_entity(ent)

    assert layout.anchor_x == 30.0
    assert layout.anchor_y == 40.0
    assert layout.height_mm == 3.5
    assert layout.halign == int(ent.dxf.halign)
    assert layout.valign == int(ent.dxf.valign)


def test_normalize_attdef_uses_align_point_for_middle_center() -> None:
    """ATTDEF middle-center anchor should resolve from align_point."""

    doc = _new_doc()
    blk = doc.blocks.new("B")
    ent = blk.add_attdef("TAG", (10.0, 20.0), "abc", height=3.0)
    ent.set_placement((30.0, 40.0), align=TextEntityAlignment.MIDDLE_CENTER)

    layout = normalize_dxf_text_entity(ent)

    assert layout.anchor_x == 30.0
    assert layout.anchor_y == 40.0
    assert layout.halign == 1
    assert layout.valign == 2


def test_normalize_attdef_left_uses_insert_even_if_align_point_exists() -> None:
    """ATTDEF left align should keep insert as rendering anchor."""

    doc = _new_doc()
    blk = doc.blocks.new("B")
    ent = blk.add_attdef("TAG", (10.0, 20.0), "abc", height=3.0)
    ent.dxf.align_point = (90.0, 80.0, 0.0)

    layout = normalize_dxf_text_entity(ent)

    assert layout.anchor_x == 10.0
    assert layout.anchor_y == 20.0
    assert layout.halign == 0
    assert layout.render_halign == 0
    assert layout.render_valign == 0


def test_normalize_attdef_middle_maps_to_render_center_middle() -> None:
    """DXF MIDDLE(halign=4) should render as center-middle at align point."""

    doc = _new_doc()
    blk = doc.blocks.new("B")
    ent = blk.add_attdef("TAG", (10.0, 20.0), "abc", height=3.0)
    ent.dxf.halign = 4
    ent.dxf.valign = 0
    ent.dxf.align_point = (30.0, 40.0, 0.0)

    layout = normalize_dxf_text_entity(ent)

    assert layout.halign == 4
    assert layout.valign == 0
    assert layout.anchor_x == 30.0
    assert layout.anchor_y == 40.0
    assert layout.render_halign == 1
    assert layout.render_valign == 2
    assert layout.render_fit_mode == "none"


def test_normalize_attdef_fit_maps_to_baseline_length_mode() -> None:
    """DXF FIT should expose baseline-fit render parameters for UI path drawing."""

    doc = _new_doc()
    blk = doc.blocks.new("B")
    ent = blk.add_attdef("TAG", (10.0, 20.0), "abc", height=3.0)
    ent.dxf.halign = 5
    ent.dxf.valign = 0
    ent.dxf.align_point = (40.0, 20.0, 0.0)

    layout = normalize_dxf_text_entity(ent)

    assert layout.anchor_x == 10.0
    assert layout.anchor_y == 20.0
    assert layout.render_halign == 0
    assert layout.render_valign == 0
    assert layout.render_rotation_deg == 0.0
    assert layout.render_fit_mode == "fit"
    assert abs(layout.render_fit_length_mm - 30.0) < 1e-6


def test_normalize_attdef_aligned_maps_to_rotation_and_fit_mode() -> None:
    """DXF ALIGNED should rotate baseline and use aligned-fit mode."""

    doc = _new_doc()
    blk = doc.blocks.new("B")
    ent = blk.add_attdef("TAG", (10.0, 20.0), "abc", height=3.0)
    ent.dxf.halign = 3
    ent.dxf.valign = 0
    ent.dxf.align_point = (10.0, 30.0, 0.0)

    layout = normalize_dxf_text_entity(ent)

    assert layout.anchor_x == 10.0
    assert layout.anchor_y == 20.0
    assert layout.render_halign == 0
    assert layout.render_valign == 0
    assert abs(layout.render_rotation_deg - 90.0) < 1e-6
    assert layout.render_fit_mode == "aligned"
    assert abs(layout.render_fit_length_mm - 10.0) < 1e-6


def test_normalize_mtext_preserves_height_width_and_attachment() -> None:
    """MTEXT normalization keeps TOC fallback geometry semantics.

    Returns:
        None
    """

    doc = _new_doc()
    msp = doc.modelspace()
    ent = msp.add_mtext(
        "line1\\Pline2\\P日本語",
        dxfattribs={
            # Same semantics as toc_frame_service fallback MTEXT.
            "char_height": 2.8,
            "width": 175.0,
            "insert": (18.0, 250.0),
            "attachment_point": 1,
        },
    )

    layout = normalize_dxf_text_entity(ent)

    assert layout.is_multiline is True
    assert layout.text == "line1\nline2\n日本語"
    assert layout.height_mm == 2.8
    assert layout.width_mm == 175.0
    assert layout.anchor_x == 18.0
    assert layout.anchor_y == 250.0
    assert layout.attachment_point == 1
    assert layout.halign == 0
    assert layout.valign == 3


def test_decode_dxf_unicode_escapes_decodes_u_plus_sequence() -> None:
    """DXF special unicode escape should decode to actual character."""

    assert decode_dxf_unicode_escapes(r"\U+3042abc") == "あabc"


def test_build_single_line_layout_for_user_text_defaults() -> None:
    """Programmatic single-line text should normalize to non-empty defaults.

    Returns:
        None
    """

    layout = build_single_line_layout(text="USER_TEXT", insert_x=1.0, insert_y=2.0, height_mm=2.5)

    assert layout.is_multiline is False
    assert layout.text == "USER_TEXT"
    assert layout.anchor_x == 1.0
    assert layout.anchor_y == 2.0
    assert layout.height_mm == 2.5
    assert layout.font_family
    assert layout.font_families
    assert layout.font_families[-1] == "sans-serif"


def test_font_family_candidates_include_cjk_families() -> None:
    """Font candidates should include CJK-capable families for Japanese text.

    Returns:
        None
    """

    cands = font_family_candidates()
    assert "Yu Gothic" in cands
    assert "Noto Sans CJK JP" in cands


def test_ui_font_family_chain_prioritizes_preferred_and_qt_fallback() -> None:
    """Preferred family should be first and generic Qt fallback should exist.

    Returns:
        None
    """

    chain = ui_font_family_chain("MS Gothic")
    assert chain[0] == "MS Gothic"
    assert "Yu Gothic UI" in chain
    assert chain[-1] == "sans-serif"


def test_ui_font_family_chain_project_preferred_font_first() -> None:
    """Project setting should precede DXF-style preferred family when set."""

    chain = ui_font_family_chain("Arial", project_preferred_font="Meiryo")
    assert chain[0] == "Meiryo"
    assert chain[1] == "Arial"


def test_ui_font_family_chain_project_default_skips_extra_layer() -> None:
    """Empty project preference should match legacy order (DXF first)."""

    chain_legacy = ui_font_family_chain("Consolas")
    chain_empty = ui_font_family_chain("Consolas", project_preferred_font=None)
    chain_blank = ui_font_family_chain("Consolas", project_preferred_font="")
    assert chain_legacy == chain_empty == chain_blank


def test_normalize_text_uses_style_font_file_stem_alias() -> None:
    """DXF style font file stem should map to a practical UI family name.

    Returns:
        None
    """

    doc = _new_doc()
    std = doc.styles.get("Standard")
    std.dxf.font = "msgothic.ttc"
    msp = doc.modelspace()
    ent = msp.add_text("abc", height=2.5, dxfattribs={"style": "Standard", "insert": (0.0, 0.0)})

    layout = normalize_dxf_text_entity(ent)

    assert layout.font_family == "MS Gothic"
    assert layout.font_families[0] == "MS Gothic"
    assert layout.font_families[-1] == "sans-serif"


def test_font_family_preferred_for_style_table_key_matches_entity_layout() -> None:
    """TEXTSTYLE table key should resolve the same preferred family as UI entities."""

    doc = _new_doc()
    doc.styles.add("CustomStyle", font="msgothic.ttc")
    msp = doc.modelspace()
    ent = msp.add_text(
        "abc",
        height=2.5,
        dxfattribs={"style": "CustomStyle", "insert": (0.0, 0.0)},
    )
    layout = normalize_dxf_text_entity(ent)
    key = make_table_key("CustomStyle")
    assert font_family_preferred_for_style_table_key(doc, key) == layout.font_family


def test_font_family_preferred_for_unknown_style_table_key_falls_back() -> None:
    """Missing TEXTSTYLE for a key should fall back like unspecified UI style."""

    doc = _new_doc()
    bogus_key = make_table_key("__no_such_style__")
    assert font_family_preferred_for_style_table_key(doc, bogus_key) == preferred_ui_font_family(None)


def test_apply_render_context_fonts_uses_distinct_faces_per_style() -> None:
    """PDF RenderContext fonts must not collapse all styles to one face."""

    doc = _new_doc()
    doc.styles.add("PdfStyleA", font="msgothic.ttc")
    doc.styles.add("PdfStyleB", font="arial.ttf")
    ctx = RenderContext(doc)

    def _fake_resolve(pref: str, **kwargs: object) -> fonts.FontFace:
        return fonts.FontFace(filename=f"/mock/{pref.replace(' ', '_')}")

    with patch(
        "logic_cad.core.text.layout_resolver.resolve_pdf_font_face_for_ui_family_chain",
        side_effect=_fake_resolve,
    ):
        apply_render_context_fonts_for_pdf_like_ui(ctx, doc)

    fa = ctx.fonts[make_table_key("PdfStyleA")]
    fb = ctx.fonts[make_table_key("PdfStyleB")]
    assert fa.filename != fb.filename


def test_apply_render_context_fonts_keeps_ezdxf_face_when_chain_unresolved() -> None:
    """When no OS font matches the UI chain, keep ezdxf's resolved FontFace."""

    doc = _new_doc()
    ctx = RenderContext(doc)
    before = {k: ctx.fonts[k] for k in ctx.fonts.keys()}
    with patch(
        "logic_cad.core.text.layout_resolver.resolve_pdf_font_face_for_ui_family_chain",
        return_value=None,
    ):
        apply_render_context_fonts_for_pdf_like_ui(ctx, doc)
    for k in before:
        assert ctx.fonts[k] is before[k]


def test_mtext_single_line_height_matches_text_rule() -> None:
    """Single-line MTEXT should use nearly same mm-height as TEXT path rule.

    Returns:
        None
    """

    _ensure_qt_app()
    cap = 3.0
    txt = "MTEXT size parity"
    r_text = text_path_bounds_item_local(txt, cap, QPointF(0.0, 0.0), halign=0, valign=3)
    r_mtx = mtext_path_bounds_item_local(txt, cap, halign=0, valign=3)
    assert r_text is not None and r_mtx is not None
    assert abs(r_text.height() - r_mtx.height()) <= 0.2


def test_mtext_wrap_respects_width_limit() -> None:
    """MTEXT bounds should respect width cap when wrapping is enabled.

    Returns:
        None
    """

    _ensure_qt_app()
    r = mtext_path_bounds_item_local(
        "one two three four five six seven",
        2.8,
        width_mm=24.0,
        halign=0,
        valign=3,
    )
    assert r is not None
    assert r.width() <= 24.6


def test_pdf_like_font_table_matches_render_context_apply() -> None:
    """Cached table builder must match PDF RenderContext.fonts after apply."""

    doc = _new_doc()
    table = build_pdf_like_font_face_table(doc)
    ctx = RenderContext(doc)
    apply_render_context_fonts_for_pdf_like_ui(ctx, doc)
    assert table.keys() == ctx.fonts.keys()
    for key in table:
        assert table[key] is ctx.fonts[key]


def test_get_pdf_like_font_face_table_uses_cache_until_invalidated() -> None:
    """Document cache should return the same mapping until invalidate."""

    doc = _new_doc()
    first = get_pdf_like_font_face_table(doc)
    second = get_pdf_like_font_face_table(doc)
    assert first is second
    invalidate_pdf_like_font_face_cache(doc=doc)
    third = get_pdf_like_font_face_table(doc)
    assert third is not first


def test_normalize_dxf_text_entity_sets_outline_font_face() -> None:
    """Normalized layout should carry PDF-aligned outline font face for Qt."""

    doc = _new_doc()
    msp = doc.modelspace()
    ent = msp.add_text("abc", height=2.5, dxfattribs={"style": "Standard", "insert": (0.0, 0.0)})
    layout = normalize_dxf_text_entity(ent)
    table = get_pdf_like_font_face_table(doc)
    std_key = make_table_key("Standard")
    assert layout.outline_font_face is table.get(std_key)


def test_qfont_from_font_face_uses_prefer_no_font_merging() -> None:
    """Qt path text should opt out of font merging when building QFont."""

    _ensure_qt_app()
    font = _qfont_from_font_face(None, font_family="Arial")
    no_merge = getattr(
        QFont.StyleStrategy,
        "PreferNoFontMerging",
        QFont.StyleStrategy.NoFontMerging,
    )
    assert font.styleStrategy() & no_merge
