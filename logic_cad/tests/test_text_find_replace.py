"""Find/replace service: SYM/LABEL* and USER_TEXT; exclusions."""

from __future__ import annotations

import re

import pytest

from logic_cad.core.attrib_tags import is_find_replace_attrib_tag
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import ENTITY_TYPE_USER_TEXT, USER_TEXT_DEFAULT_HEIGHT_MM
from logic_cad.core.model.xdata import get_type
from logic_cad.core.services.text_find_replace import (
    list_text_search_hits,
    text_count_matches,
    text_find_replace,
)
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.tests.test_symbol_optional_attribs import _add_optional_alarm_block


def test_is_find_replace_allows_sym_and_label_not_static() -> None:
    assert is_find_replace_attrib_tag("SYM")
    assert is_find_replace_attrib_tag("LABEL0")
    assert is_find_replace_attrib_tag("label1")
    assert not is_find_replace_attrib_tag("STATIC_LABEL0")
    assert not is_find_replace_attrib_tag("DWG_NO")


def test_replace_sym_case_insensitive_by_default() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        uid = d.place_symbol("NOT", (9.0, 9.0), "N1")
    n = text_find_replace(
        d,
        [layout],
        "n1",
        "M1",
        match_case=False,
        use_regex=True,
        apply=True,
    )
    assert n == 1
    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    sym = next(a for a in ins.attribs if str(a.dxf.tag) == "SYM")
    assert str(sym.dxf.text) == "M1"


def test_replace_sym_respects_match_case() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        uid = d.place_symbol("NOT", (9.0, 9.0), "N1")
    n = text_find_replace(
        d,
        [layout],
        "n1",
        "M1",
        match_case=True,
        use_regex=True,
        apply=True,
    )
    assert n == 0
    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    sym0 = str(next(a for a in ins.attribs if str(a.dxf.tag) == "SYM").dxf.text)
    assert sym0 == "N1"


def test_literal_substring_not_regex_meta() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        uid = d.place_symbol("NOT", (5.0, 5.0), "A.B")
    n = text_find_replace(
        d,
        [layout],
        ".",
        "X",
        match_case=True,
        use_regex=False,
        apply=True,
    )
    assert n == 1
    sym = str(
        next(a for a in d.symbols.insert_by_uid(layout, uid).attribs if str(a.dxf.tag) == "SYM").dxf.text
    )
    assert sym == "AXB"


def test_literal_repl_backslash_not_backref() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        uid = d.place_symbol("NOT", (1.0, 1.0), "Q1")
    n = text_find_replace(
        d,
        [layout],
        "1",
        r"\1Z",
        match_case=True,
        use_regex=False,
        apply=True,
    )
    assert n == 1
    sym = str(
        next(a for a in d.symbols.insert_by_uid(layout, uid).attribs if str(a.dxf.tag) == "SYM").dxf.text
    )
    assert sym == r"Q\1Z"


def test_static_label_unchanged_label_changed() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    _add_optional_alarm_block(d, "ALARM_FR")
    with d.begin("p"):
        uid = d.place_symbol("ALARM_FR", (5.0, 5.0), "A1")
        d.set_symbol_attr(uid, "STATIC_LABEL0", "hold")
        d.set_symbol_attr(uid, "LABEL0", "hold")
    n = text_find_replace(
        d,
        [layout],
        "hold",
        "gone",
        match_case=False,
        use_regex=True,
        apply=True,
    )
    assert n == 1
    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    m = {str(a.dxf.tag): str(a.dxf.text) for a in ins.attribs}
    assert m["STATIC_LABEL0"] == "hold"
    assert m["LABEL0"] == "gone"


def test_user_text_replaced() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("t"):
        uid = d.add_user_text((20.0, 20.0), "alpha-beta", USER_TEXT_DEFAULT_HEIGHT_MM)
    n = text_find_replace(
        d,
        [layout],
        "beta",
        "gamma",
        match_case=False,
        use_regex=True,
        apply=True,
    )
    assert n == 1
    ent = find_entity_by_uid(d.doc, uid)
    assert ent is not None
    assert get_type(ent) == ENTITY_TYPE_USER_TEXT
    assert str(ent.dxf.text) == "alpha-gamma"


def _sym_text(d: LogicDiagram, layout: str, uid: str) -> str:
    ins = d.symbols.insert_by_uid(layout, uid)
    assert ins is not None
    a = next(x for x in ins.attribs if str(x.dxf.tag) == "SYM")
    return str(a.dxf.text)


def test_scope_current_page_only() -> None:
    d = LogicDiagram.new()
    p1 = d.current_layout_name
    d.add_page("02")
    with d.begin("a"):
        u1 = d.place_symbol("NOT", (1.0, 1.0), "A1")
    d.current_layout_name = "02"
    p2 = d.current_layout_name
    with d.begin("b"):
        u2 = d.place_symbol("NOT", (2.0, 2.0), "A2")
    n = text_find_replace(
        d,
        [p2],
        "A2",
        "B2",
        match_case=False,
        use_regex=True,
        apply=True,
    )
    assert n == 1
    assert _sym_text(d, p1, u1) == "A1"
    assert _sym_text(d, p2, u2) == "B2"


def test_text_count_matches_matches_text_find_replace_dry() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        d.place_symbol("NOT", (1.0, 1.0), "X")
    a = text_count_matches(
        d,
        [layout],
        "X",
        match_case=True,
        use_regex=True,
    )
    b = text_find_replace(
        d,
        [layout],
        "X",
        "_",
        match_case=True,
        use_regex=True,
        apply=False,
    )
    assert a == b == 1


def test_invalid_regex_raises() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with pytest.raises(re.error):
        text_find_replace(
            d,
            [layout],
            "[",
            "x",
            match_case=False,
            use_regex=True,
            apply=False,
        )


def test_invalid_bracket_not_error_when_not_regex() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("p"):
        d.place_symbol("NOT", (1.0, 1.0), "[a]")
    n = text_find_replace(
        d,
        [layout],
        "[a]",
        "ok",
        match_case=True,
        use_regex=False,
        apply=True,
    )
    assert n == 1


def test_list_text_search_hits_symbol_and_user_text() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("x"):
        d.place_symbol("NOT", (5.0, 5.0), "foo")
        d.add_user_text((10.0, 10.0), "foo", USER_TEXT_DEFAULT_HEIGHT_MM)
    hits = list_text_search_hits(d, [layout], "foo", match_case=True, use_regex=True)
    assert len(hits) == 2
    assert {h.kind for h in hits} == {"symbol", "user_text"}
    n = text_count_matches(d, [layout], "foo", match_case=True, use_regex=True)
    assert n == 2


def test_list_hits_one_field_multi_subn_still_one_row() -> None:
    """Multiple non-overlapping matches in one string: one TextSearchHit, count > 1."""
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("x"):
        d.place_symbol("NOT", (5.0, 5.0), "aa")
    n = text_count_matches(d, [layout], "a", match_case=True, use_regex=True)
    assert n == 2
    hits = list_text_search_hits(d, [layout], "a", match_case=True, use_regex=True)
    assert len(hits) == 1
    assert hits[0].kind == "symbol"
