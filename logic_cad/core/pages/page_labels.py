"""Page labels for cross-page refs (shared suffix so humans can match links across sheets)."""

from __future__ import annotations


def page_index_to_letters(idx: int) -> str:
    """Map 0-based page index to column letters (A..Z, AA, AB, …)."""
    n = idx + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def letters_to_page_index(letters: str) -> int | None:
    """Inverse of ``page_index_to_letters``: A→0, B→1, …; ``None`` if invalid."""
    s = str(letters or "").strip().upper()
    if not s:
        return None
    for c in s:
        if not ("A" <= c <= "Z"):
            return None
    val = 0
    for c in s:
        val = val * 26 + (ord(c) - 64)
    return val - 1


def page_ref_link_label(target_layout: str, ordinal: int) -> str:
    """PAGE_REF SYM on one sheet: same *target_layout* gets ``A``, ``B``, … ``Z``, ``AA``, … (ordinal 0, 1, …)."""
    return f"{target_layout} {page_index_to_letters(ordinal)}"


def page_symbol_label(layout_name: str, pages: list[str]) -> str:
    """Short hint text (palette, etc.): ``{name} A`` for normal sheets; not the same as PAGE_REF SYM."""
    # Local import: page_order imports this module; hoisting would create an import cycle.
    from logic_cad.core.pages.page_order import is_toc_layout_name

    if layout_name not in pages:
        return layout_name
    if is_toc_layout_name(layout_name):
        return layout_name
    return f"{layout_name} A"
