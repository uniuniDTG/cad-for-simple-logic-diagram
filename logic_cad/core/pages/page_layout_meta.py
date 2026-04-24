"""LAYOUT entity XDATA (type PAGE): description and revision only.

The unique page identifier is **ezdxf layout name** (``doc.layouts``). This XDATA does not
store ``page_id`` or ``page_name``; use ``layout_name`` everywhere in code.
"""

from __future__ import annotations

from ezdxf.document import Drawing

from logic_cad.core.model.xdata import build_ld_app_tags, new_uid, read_ld_app_dict, set_entity_xdata

_STRIP_PAGE_KEYS = frozenset({"page_id", "page_name"})


def read_page_meta(doc: Drawing, layout_name: str) -> dict[str, str]:
    layout = doc.layouts.get(layout_name)
    le = getattr(layout, "dxf_layout", None)
    if le is None:
        return {}
    d = read_ld_app_dict(le)
    for k in _STRIP_PAGE_KEYS:
        d.pop(k, None)
    return d


def read_drawing_number(doc: Drawing) -> str:
    """Drawing-wide number / ID (stored in DXF header ``$PROJECTNAME`` for CAD compatibility)."""
    v = doc.header.get("$PROJECTNAME")
    if v is None:
        return ""
    return str(v).strip()


def read_drawing_page_start(doc: Drawing) -> int:
    """First sheet's displayed page number for ``{{PAGE_NUM}}`` (DXF header ``$USERI1``; default 1)."""

    v = doc.header.get("$USERI1")
    try:
        n = int(v) if v is not None else 0
    except (TypeError, ValueError):
        n = 0
    return n if n >= 1 else 1


def read_drawing_page_total_override(doc: Drawing) -> int | None:
    """Override for ``{{PAGE_TOTAL}}`` (``$USERI2``). ``None`` = use current paper layout count."""

    v = doc.header.get("$USERI2")
    try:
        n = int(v) if v is not None else 0
    except (TypeError, ValueError):
        n = 0
    return n if n >= 1 else None


def merge_layout_page_xdata(doc: Drawing, layout_name: str, **updates: str | None) -> None:
    """Merge keys into LAYOUT LD_APP (type PAGE). None skips that key."""
    layout = doc.layouts.get(layout_name)
    le = layout.dxf_layout
    d = read_ld_app_dict(le)
    uid = d.get("uid") or new_uid()
    for k, v in updates.items():
        if v is not None:
            d[k] = v
    for k in _STRIP_PAGE_KEYS:
        d.pop(k, None)
    extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
    tags = build_ld_app_tags("1", uid, "PAGE", extra)
    set_entity_xdata(le, tags)
