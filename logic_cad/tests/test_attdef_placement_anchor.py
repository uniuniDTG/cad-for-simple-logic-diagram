"""ATTDEF anchor normalization tests for UI rendering."""

from types import SimpleNamespace

import ezdxf

from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity


def test_attdef_anchor_middle_center_uses_align_point() -> None:
    d = ezdxf.new()
    b = d.blocks.new("B")
    e = b.add_attdef("TAG", (0, 0), "TEXT")
    e.dxf.halign = 1
    e.dxf.valign = 2
    e.dxf.align_point = (5, 5, 0)
    layout = normalize_dxf_text_entity(e)
    assert layout.anchor_x == 5.0 and layout.anchor_y == 5.0
    assert layout.halign == 1
    assert layout.valign == 2


def test_attdef_anchor_left_uses_insert_despite_align_point() -> None:
    d = ezdxf.new()
    b = d.blocks.new("B")
    e = b.add_attdef("TAG", (1, 2), "TEXT")
    e.dxf.align_point = (99, 99, 0)
    layout = normalize_dxf_text_entity(e)
    assert layout.anchor_x == 1.0 and layout.anchor_y == 2.0
    assert layout.halign == 0


def test_attdef_anchor_falls_back_to_insert_without_get_placement() -> None:
    ent = SimpleNamespace(
        dxf=SimpleNamespace(
            insert=SimpleNamespace(x=3.0, y=4.0),
            text="T",
            height=2.5,
            rotation=0.0,
            width=1.0,
            halign=0,
            valign=0,
            style="Standard",
        ),
        dxftype=lambda: "ATTDEF",
        doc=None,
    )
    layout = normalize_dxf_text_entity(ent)  # type: ignore[arg-type]
    assert layout.anchor_x == 3.0 and layout.anchor_y == 4.0


def test_attdef_anchor_uses_align_point_without_get_placement() -> None:
    ent = SimpleNamespace(
        dxf=SimpleNamespace(
            insert=SimpleNamespace(x=3.0, y=4.0),
            align_point=SimpleNamespace(x=8.0, y=9.0),
            text="T",
            height=2.5,
            rotation=0.0,
            width=1.0,
            halign=1,
            valign=0,
            style="Standard",
        ),
        dxftype=lambda: "ATTDEF",
        doc=None,
    )
    layout = normalize_dxf_text_entity(ent)  # type: ignore[arg-type]
    assert layout.anchor_x == 8.0 and layout.anchor_y == 9.0


def test_attdef_middle_render_alignment_without_get_placement() -> None:
    ent = SimpleNamespace(
        dxf=SimpleNamespace(
            insert=SimpleNamespace(x=3.0, y=4.0),
            align_point=SimpleNamespace(x=8.0, y=9.0),
            text="T",
            height=2.5,
            rotation=0.0,
            width=1.0,
            halign=4,
            valign=0,
            style="Standard",
        ),
        dxftype=lambda: "ATTDEF",
        doc=None,
    )
    layout = normalize_dxf_text_entity(ent)  # type: ignore[arg-type]
    assert layout.anchor_x == 8.0 and layout.anchor_y == 9.0
    assert layout.render_halign == 1
    assert layout.render_valign == 2
