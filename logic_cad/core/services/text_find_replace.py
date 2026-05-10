"""Project-wide find/replace for logic labels and user annotation text."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from logic_cad.core.attrib_tags import is_find_replace_attrib_tag
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.constants import (
    ENTITY_TYPE_INPAGE_REF,
    ENTITY_TYPE_TOC_HEADER,
    ENTITY_TYPE_TOC_ROW,
    ENTITY_TYPE_USER_TEXT,
    USER_TEXT_DEFAULT_HEIGHT_MM,
)
from logic_cad.core.model.xdata import get_type, get_uid
from logic_cad.core.paper_layout_access import paper_layout_block

# PAGE_REF uses literal "PAGE_REF" in XDATA; there is no ENTITY_TYPE constant in :mod:`constants`.
_SKIP_SYMBOL_TYPES: frozenset[str] = frozenset(
    {
        "PAGE_REF",
        ENTITY_TYPE_INPAGE_REF,
        ENTITY_TYPE_TOC_HEADER,
        ENTITY_TYPE_TOC_ROW,
    }
)


@dataclass(frozen=True)
class TextSearchHit:
    """One symbol attrib or user-text field that matches; one hit per field even if multiple substrings match."""

    layout_name: str
    kind: Literal["symbol", "user_text"]
    uid: str
    symbol_attrib_tag: str | None


def list_text_search_hits(
    diagram: LogicDiagram,
    layout_names: list[str],
    pattern: str,
    *,
    match_case: bool = False,
    use_regex: bool = True,
) -> list[TextSearchHit]:
    """List each eligible text field with at least one match, in stable scan order.

    Order matches :func:`text_find_replace` (layout list order, then block entity order, attribs
    order). The sum of per-field ``subn`` counts equals :func:`text_count_matches` for the same
    *pattern* and flags.

    Args:
        diagram: Active diagram.
        layout_names: Paper layout names to scan.
        pattern: User search (regex or literal per *use_regex*).
        match_case: Case-sensitive when True.
        use_regex: Regex vs literal.

    Returns:
        One :class:`TextSearchHit` per field with any match (not one per match occurrence).

    Raises:
        re.error: If *use_regex* is True and the pattern is invalid.
    """
    rx = _compile_find_pattern(pattern, match_case=match_case, use_regex=use_regex)
    out: list[TextSearchHit] = []
    doc = diagram.doc

    for layout_name in layout_names:
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, layout_name)
        if blk is None:
            continue
        for e in blk:
            dt = e.dxftype()
            if dt == "INSERT":
                uid = get_uid(e)
                if not uid:
                    continue
                et = get_type(e) or ""
                if et in _SKIP_SYMBOL_TYPES:
                    continue
                for a in e.attribs:
                    tag = str(a.dxf.tag)
                    if not is_find_replace_attrib_tag(tag):
                        continue
                    old = str(a.dxf.text or "")
                    _new, n = _subn(old, rx, "", use_regex=use_regex)
                    if n > 0:
                        out.append(
                            TextSearchHit(
                                layout_name=layout_name,
                                kind="symbol",
                                uid=uid,
                                symbol_attrib_tag=tag,
                            )
                        )
            elif dt == "TEXT":
                if get_type(e) != ENTITY_TYPE_USER_TEXT:
                    continue
                uid = get_uid(e)
                if not uid:
                    continue
                old = str(e.dxf.text or "")
                _new, n = _subn(old, rx, "", use_regex=use_regex)
                if n > 0:
                    out.append(
                        TextSearchHit(
                            layout_name=layout_name,
                            kind="user_text",
                            uid=uid,
                            symbol_attrib_tag=None,
                        )
                    )

    return out


def _compile_find_pattern(
    pattern: str,
    *,
    match_case: bool,
    use_regex: bool,
) -> re.Pattern[str]:
    """Compile the search pattern (regex or re.escape-literal for whole-string matches).

    Args:
        pattern: User search string.
        match_case: If True, search is case-sensitive; if False, use :data:`re.IGNORECASE`.
        use_regex: If False, *pattern* is treated as a literal (``re.escape`` before compile).

    Returns:
        Compiled pattern.

    Raises:
        re.error: If *use_regex* is True and *pattern* is not a valid regular expression.
    """
    flags = 0 if match_case else re.IGNORECASE
    source = pattern if use_regex else re.escape(pattern)
    return re.compile(source, flags)


def _subn(
    old: str,
    rx: re.Pattern[str],
    repl: str,
    *,
    use_regex: bool,
) -> tuple[str, int]:
    """Replace in *old*; when not regex mode, *repl* is always literal (no ``\\1``)."""
    if use_regex:
        return rx.subn(repl, old, count=0)
    return rx.subn(lambda _m: repl, old, count=0)


def text_count_matches(
    diagram: LogicDiagram,
    layout_names: list[str],
    pattern: str,
    *,
    match_case: bool = False,
    use_regex: bool = True,
) -> int:
    """Count how many non-overlapping matches would occur (same as replace count for empty repl).

    Does not change the document.

    Args:
        diagram: Active diagram.
        layout_names: Paper layout names to scan.
        pattern: Find string.
        match_case: Case-sensitive when True.
        use_regex: Regex vs literal find string.

    Returns:
        Total match count (sum over eligible fields / ``subn`` counts).

    Raises:
        re.error: If *use_regex* is True and the pattern is invalid.
    """
    return text_find_replace(
        diagram,
        layout_names,
        pattern,
        "",
        match_case=match_case,
        use_regex=use_regex,
        apply=False,
    )


def text_find_replace(
    diagram: LogicDiagram,
    layout_names: list[str],
    pattern: str,
    repl: str,
    *,
    match_case: bool = False,
    use_regex: bool = True,
    apply: bool = True,
) -> int:
    """Count or perform replace on ``SYM``/``LABEL*`` attribs and ``USER_TEXT`` entities.

    Skips page/in-page ref symbols, TOC grid inserts, static/frame tags (see
    :func:`~logic_cad.core.attrib_tags.is_find_replace_attrib_tag`).

    Args:
        diagram: Active diagram (uses ``doc``, ``symbols``, ``user_geom``).
        layout_names: Paper layout names to scan (no model space).
        pattern: User search (regex or literal depending on *use_regex*).
        repl: Replacement string. When *use_regex* is True, backreferences in *repl* work as in
            :func:`re.subn`. When False, *repl* is always a literal.
        match_case: If True, case-sensitive; if False, use :data:`re.IGNORECASE` on the pattern.
        use_regex: If False, *pattern* is searched as a literal substring (via ``re.escape``), and
            *repl* is inserted literally.
        apply: If False, do not mutate; only return the would-be ``subn`` count.

    Returns:
        Total number of non-overlapping matches / substitutions (sum of ``subn`` counts per field).

    Raises:
        re.error: If *use_regex* is True and the pattern is not a valid regular expression.
    """
    rx = _compile_find_pattern(pattern, match_case=match_case, use_regex=use_regex)
    total = 0
    doc = diagram.doc
    symbols = diagram.symbols
    user_geom = diagram.user_geom

    for layout_name in layout_names:
        layout = doc.layouts.get(layout_name)
        if layout is None or layout.is_modelspace:
            continue
        blk = paper_layout_block(doc, layout_name)
        if blk is None:
            continue
        for e in blk:
            dt = e.dxftype()
            if dt == "INSERT":
                total += _replace_attribs_in_insert(
                    layout_name,
                    e,
                    rx,
                    repl,
                    symbols,
                    use_regex=use_regex,
                    apply=apply,
                )
            elif dt == "TEXT":
                et = get_type(e)
                if et != ENTITY_TYPE_USER_TEXT:
                    continue
                uid = get_uid(e)
                if not uid:
                    continue
                old = str(e.dxf.text or "")
                _new, n = _subn(old, rx, repl, use_regex=use_regex)
                if n == 0:
                    continue
                total += n
                if apply:
                    h = float(
                        getattr(e.dxf, "height", USER_TEXT_DEFAULT_HEIGHT_MM)
                        or USER_TEXT_DEFAULT_HEIGHT_MM
                    )
                    user_geom.set_user_text_props(layout_name, uid, _new, h)

    return total


def _replace_attribs_in_insert(
    layout_name: str,
    ins,
    rx: re.Pattern[str],
    repl: str,
    symbols,
    *,
    use_regex: bool,
    apply: bool,
) -> int:
    """Run replace on eligible attribs of one INSERT. Returns subn sum."""
    uid = get_uid(ins)
    if not uid:
        return 0
    et = get_type(ins) or ""
    if et in _SKIP_SYMBOL_TYPES:
        return 0
    total = 0
    for a in ins.attribs:
        tag = str(a.dxf.tag)
        if not is_find_replace_attrib_tag(tag):
            continue
        old = str(a.dxf.text or "")
        new, n = _subn(old, rx, repl, use_regex=use_regex)
        if n == 0:
            continue
        total += n
        if apply:
            symbols.set_symbol_attr(layout_name, uid, tag, new)
    return total
