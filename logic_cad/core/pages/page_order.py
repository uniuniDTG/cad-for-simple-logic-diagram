"""Paper layout name order (natural sort), tab order on save, TOC layout names (0, 0A, 0B, …)."""

from __future__ import annotations

import re
from collections.abc import Iterable

from ezdxf.document import Drawing

from logic_cad.core.pages.page_labels import page_index_to_letters

_PAPER_LAYOUT_NAME_RE = re.compile(r"^[A-Za-z0-9_]+$")
# TOC paper layouts use the same strings as reserved slot ids: 0, 0A, 0B, …
_RESERVED_TOC_LAYOUT_NAME_RE = re.compile(r"^0[A-Z]*$")


def validate_paper_layout_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a valid paper layout name."""
    s = str(name).strip()
    if not s:
        raise ValueError("レイアウト名を空にすることはできません。")
    if not _PAPER_LAYOUT_NAME_RE.fullmatch(s):
        raise ValueError(
            f"レイアウト名 {name!r} は無効です。使用できるのは英数字とアンダースコアのみです。"
        )


def _natural_sort_key(layout_name: str) -> tuple:
    parts = re.split(r"(\d+)", layout_name)
    key: list = []
    for p in parts:
        if not p:
            continue
        if p.isdigit():
            key.append((0, int(p)))
        else:
            key.append((1, p.lower()))
    return tuple(key)


def _toc_slot_index(layout_name: str) -> int | None:
    for i in range(512):
        if toc_page_id_for_slot(i) == layout_name:
            return i
    return None


def sort_paper_layout_names(names: Iterable[str]) -> list[str]:
    """TOC layouts first (slot order 0, 0A, …), then other papers (natural sort: 2 < 10 < 11)."""
    names = list(names)
    toc = [n for n in names if is_toc_layout_name(n)]
    rest = [n for n in names if not is_toc_layout_name(n)]

    def toc_key(n: str) -> int:
        idx = _toc_slot_index(n)
        return idx if idx is not None else 9999

    toc.sort(key=toc_key)
    rest.sort(key=_natural_sort_key)
    return toc + rest


def list_paper_layout_names_sorted(doc: Drawing) -> list[str]:
    raw = [L.name for L in doc.layouts if not L.is_modelspace]
    return sort_paper_layout_names(raw)


def is_toc_layout_name(layout_name: str) -> bool:
    """True if *layout_name* is a TOC sheet name (``0``, ``0A``, ``0B``, …)."""
    return is_reserved_toc_page_id(layout_name)


def toc_layout_names_sorted(doc: Drawing) -> list[str]:
    return [n for n in list_paper_layout_names_sorted(doc) if is_toc_layout_name(n)]


def toc_page_id_for_slot(index: int) -> str:
    """Slot 0 → ``0``; 1 → ``0A``; 2 → ``0B``; … using ``page_index_to_letters`` for longer suffixes."""
    if index == 0:
        return "0"
    return "0" + page_index_to_letters(index - 1)


def is_reserved_toc_page_id(pid: str) -> bool:
    s = str(pid).strip()
    return bool(_RESERVED_TOC_LAYOUT_NAME_RE.fullmatch(s))


def apply_paper_layout_taborder_by_name(doc: Drawing) -> None:
    """Set ``taborder`` so CAD tabs follow ``list_paper_layout_names_sorted`` (Model stays 0)."""
    doc.layouts.modelspace().dxf.taborder = 0
    for i, name in enumerate(list_paper_layout_names_sorted(doc), start=1):
        doc.layouts.get(name).dxf.taborder = i
