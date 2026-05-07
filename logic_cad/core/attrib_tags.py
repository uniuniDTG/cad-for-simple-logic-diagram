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


def symbol_editor_attdef_tag_choices() -> tuple[str, ...]:
    """Tags allowed in symbol block ATTDEF picker: ``SYM``, ``LABEL{{n}}``, ``STATIC_LABEL{{n}}`` only."""

    out: list[str] = ["SYM"]
    for i in range(24):
        out.append(f"LABEL{i}")
    for i in range(16):
        out.append(f"STATIC_LABEL{i}")
    return tuple(out)


def symbol_editor_attdef_tag_choices_unused_in_block(block) -> tuple[str, ...]:
    """Same as :func:`symbol_editor_attdef_tag_choices` but omitting tags already used by an ATTDEF in *block*.

    Args:
        block: ezdxf block layout (iterable of entities).

    Returns:
        Tags not yet present as ATTDEF in the block (case-insensitive).
    """

    used: set[str] = set()
    for ent in block:
        if ent.dxftype() != "ATTDEF":
            continue
        used.add(str(ent.dxf.tag).strip().upper())
    return tuple(t for t in symbol_editor_attdef_tag_choices() if str(t).strip().upper() not in used)


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
