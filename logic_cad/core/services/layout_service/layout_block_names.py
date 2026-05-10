"""Block-name lists for palette / block-editor UIs (filter system definitions)."""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.model.constants import (
    BLOCK_INPAGE_FROM,
    BLOCK_INPAGE_TO,
    BLOCK_PAGE_FROM,
    BLOCK_PAGE_TO,
    BLOCK_PAPER_FRAME,
    BLOCK_WIRE_BRANCH,
    BLOCK_CONTENTS_HEADER,
    BLOCK_CONTENTS_ROW,
)


def _iter_block_definition_names(blocks_section: object) -> list[str]:
    """Block name strings (ezdxf iter may yield str or BlockLayout depending on version)."""
    names_method = getattr(blocks_section, "names", None)
    if callable(names_method):
        try:
            return [n for n in names_method() if isinstance(n, str)]
        except (TypeError, AttributeError):
            pass
    out: list[str] = []
    for item in blocks_section:
        name = item if isinstance(item, str) else getattr(item.dxf, "name", str(item))
        out.append(name)
    return out


# Built-in blocks hidden from palette and block-editor list (TOC cells, wire-branch stub).
_CORE_SYSTEM_BLOCKS_HIDDEN_EVERYWHERE: frozenset[str] = frozenset(
    {
        BLOCK_CONTENTS_HEADER,
        BLOCK_CONTENTS_ROW,
        BLOCK_WIRE_BRANCH,
    }
)

# Page / in-page link symbols: hide from the drag palette (placement uses dedicated UI).
# ``PAGE_FROM`` / ``PAGE_TO`` stay listed in the block editor; ``INPAGE_*`` block defs do not.
_PALETTE_ONLY_HIDDEN_BLOCKS: frozenset[str] = frozenset(
    {
        BLOCK_PAGE_FROM,
        BLOCK_PAGE_TO,
        BLOCK_INPAGE_FROM,
        BLOCK_INPAGE_TO,
    }
)

_PALETTE_EXCLUDED_SYSTEM_BLOCKS: frozenset[str] = (
    _CORE_SYSTEM_BLOCKS_HIDDEN_EVERYWHERE | _PALETTE_ONLY_HIDDEN_BLOCKS
)

# BEDIT list: same as palette-hidden core blocks, plus in-page link defs (not cross-page PAGE_*).
_BLOCK_EDITOR_LIST_EXCLUDED: frozenset[str] = _CORE_SYSTEM_BLOCKS_HIDDEN_EVERYWHERE | frozenset(
    {
        BLOCK_INPAGE_FROM,
        BLOCK_INPAGE_TO,
    }
)


def _list_user_symbol_block_names(
    doc: Drawing, *, exclude: frozenset[str]
) -> list[str]:
    """Build a sorted list of block names for palette-like UIs.

    Args:
        doc: Drawing whose ``blocks`` section is scanned.
        exclude: Block definition names to omit (system / non-user symbols).

    Returns:
        Sorted names passing layout symbol filters and not in *exclude*.
    """
    out: list[str] = []
    for name in sorted(_iter_block_definition_names(doc.blocks)):
        if name.startswith("*"):
            continue
        if name == "PAGE_LINK":
            continue
        un = name.upper()
        if un.startswith("AND_") or un.startswith("OR_"):
            continue
        if name.startswith("_"):
            continue
        if name == BLOCK_PAPER_FRAME:
            continue
        if name in exclude:
            continue
        if un == "LD_CHECKPOINT":
            continue
        out.append(name)
    return out


def list_palette_block_names(doc: Drawing) -> list[str]:
    """Block definitions to offer on the palette (excludes layout helpers and gate stubs)."""
    return _list_user_symbol_block_names(doc, exclude=_PALETTE_EXCLUDED_SYSTEM_BLOCKS)


def list_block_editor_block_names(doc: Drawing) -> list[str]:
    """Block definitions listed in the BEDIT-style panel (palette-only hiddens still shown).

    ``PAGE_FROM`` / ``PAGE_TO`` are listed so cross-page link geometry can be edited;
    ``INPAGE_FROM`` / ``INPAGE_TO`` are omitted (in-page link placement uses dedicated UI).
    """
    return _list_user_symbol_block_names(doc, exclude=_BLOCK_EDITOR_LIST_EXCLUDED)
