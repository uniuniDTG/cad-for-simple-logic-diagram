"""ATTDEF tag helpers for UI (LABEL0, STATIC_LABEL0, …)."""

from __future__ import annotations

import re

from ezdxf.document import Drawing

_LABEL_ATTDEF_RE = re.compile(r"^LABEL\d+$", re.IGNORECASE)
_STATIC_LABEL_ATTDEF_RE = re.compile(r"^STATIC_LABEL\d+$", re.IGNORECASE)


FRAME_ATTDEF_TAGS = frozenset(
    {
        "DWG_NO",
        "PAGE_NAME",
        "PAGE_DESC",
        "PAGE_REV",
        "PAGE_NUM",
        "PAGE_TOTAL",
    }
)


def is_frame_attdef_tag(tag: str) -> bool:
    """ATTDEF tags for paper frame block (LD_PAPER_FRAME); drawn like symbol labels, not SYM."""
    return str(tag).strip() in FRAME_ATTDEF_TAGS


def is_supported_attdef_tag(tag: str) -> bool:
    """Tags the editor previews: SYM, STATIC_LABEL{n}, LABEL{n} (unknown tags e.g. SRC are skipped)."""
    t = str(tag).strip()
    u = t.upper()
    if u == "SYM":
        return True
    if _STATIC_LABEL_ATTDEF_RE.match(t):
        return True
    return bool(_LABEL_ATTDEF_RE.match(t))


def is_find_replace_attrib_tag(tag: str) -> bool:
    """True for attribs that global find/replace may modify: ``SYM`` or ``LABEL{n}`` only.

    Excludes ``STATIC_LABEL*``, frame fields (``FRAME_ATTDEF_TAGS``), and other tags.

    Args:
        tag: ATTRIB tag string.

    Returns:
        Whether the tag is eligible for find/replace.
    """
    t = str(tag).strip()
    if is_frame_attdef_tag(t):
        return False
    u = t.upper()
    if u == "SYM":
        return True
    if _STATIC_LABEL_ATTDEF_RE.match(t):
        return False
    return bool(_LABEL_ATTDEF_RE.match(t))


def list_editable_text_attdef_tags(doc: Drawing, block_name: str) -> list[str]:
    """TAG matching LABEL{n} or STATIC_LABEL{n} in block definition (sorted by family, then n)."""
    if block_name not in doc.blocks:
        return []
    tags: list[str] = []
    for e in doc.blocks.get(block_name):
        if e.dxftype() != "ATTDEF":
            continue
        t = str(e.dxf.tag)
        if _LABEL_ATTDEF_RE.match(t) or _STATIC_LABEL_ATTDEF_RE.match(t):
            tags.append(t)

    def sort_key(tag: str) -> tuple[int, int]:
        m = re.search(r"\d+", tag)
        idx = int(m.group()) if m else 0
        family = 0 if str(tag).upper().startswith("STATIC_LABEL") else 1
        return (family, idx)

    return sorted(tags, key=sort_key)
