"""Property panel updates from scene selection."""

from __future__ import annotations

from typing import TYPE_CHECKING

from logic_cad.core.model.constants import (
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_INPAGE_REF,
    INPAGE_SYM_HEIGHT_MM,
    INPAGE_SYM_HEIGHT_XDATA,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_CLOUD,
    ENTITY_TYPE_USER_LINE,
    ENTITY_TYPE_USER_TEXT,
    ENTITY_TYPE_WIRE_BRANCH,
    GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW,
    LINETYPE_LOGIC,
    PEER_UID_XDATA,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.model.xdata import get_type, read_ld_app_dict
from logic_cad.core.undo.history import find_entity_by_uid

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def _gate_n_from_block(name: str) -> int | None:
    for prefix in ("AND_", "OR_"):
        if name.upper().startswith(prefix):
            try:
                return int(name.split("_", 1)[1])
            except ValueError:
                return None
    return None


def on_selection_changed(win: MainWindow) -> None:
    from logic_cad.ui.items.symbol_item import SymbolItem
    from logic_cad.ui.items.user_geometry_items import UserCircleItem, UserCloudItem, UserLineItem, UserTextItem
    from logic_cad.ui.items.wire_item import WireItem

    sel = win._scene.selectedItems()
    if not sel:
        win._props.clear_selection()
        return
    if len(sel) > 1:
        win._props.show_multi(len(sel))
        return
    it = sel[0]
    if isinstance(it, WireItem):
        e = find_entity_by_uid(win._diagram.doc, it.wire_uid)
        lt = LINETYPE_LOGIC
        if e is not None and hasattr(e.dxf, "linetype"):
            raw = e.dxf.linetype
            if raw is not None and str(raw).strip():
                lt = str(raw).strip()
        win._props.show_wire(it.wire_uid, lt)
        return
    if isinstance(it, UserLineItem):
        win._props.show_user_sketch(it.sketch_uid, entity_type=ENTITY_TYPE_USER_LINE)
        return
    if isinstance(it, UserCircleItem):
        win._props.show_user_sketch(it.sketch_uid, entity_type=ENTITY_TYPE_USER_CIRCLE)
        return
    if isinstance(it, UserCloudItem):
        win._props.show_user_sketch(it.sketch_uid, entity_type=ENTITY_TYPE_USER_CLOUD)
        return
    if isinstance(it, UserTextItem):
        win._props.show_user_sketch(it.sketch_uid, entity_type=ENTITY_TYPE_USER_TEXT)
        return
    if not isinstance(it, SymbolItem):
        win._props.clear_selection()
        return
    ins = win._diagram.symbols.insert_by_uid(win._diagram.current_layout_name, it.symbol_uid)
    if ins is None:
        win._props.clear_selection()
        return
    sym_text = ins.dxf.name
    sym_visible = False
    for a in ins.attribs:
        if str(a.dxf.tag).upper() == "SYM":
            sym_text = str(a.dxf.text or sym_text)
            sym_visible = not bool(a.dxf.invisible)
            break
    t = get_type(ins)
    if t == "PAGE_REF":
        xd = read_ld_app_dict(ins)
        win._props.show_page_ref(
            it.symbol_uid,
            xd.get(TARGET_LAYOUT_XDATA, ""),
            xd.get("sym", sym_text),
            block_name=ins.dxf.name,
            entity_type=str(t),
        )
        return
    if t == ENTITY_TYPE_INPAGE_REF:
        xd = read_ld_app_dict(ins)
        sym_h: float | None = None
        raw_h = (xd.get(INPAGE_SYM_HEIGHT_XDATA) or "").strip()
        if raw_h:
            try:
                sym_h = float(raw_h)
            except ValueError:
                sym_h = None
        if sym_h is None:
            for a in ins.attribs:
                if str(a.dxf.tag).upper() == "SYM":
                    try:
                        sym_h = float(getattr(a.dxf, "height", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        sym_h = None
                    break
        if sym_h is None:
            sym_h = INPAGE_SYM_HEIGHT_MM
        win._props.show_inpage_ref(
            it.symbol_uid,
            xd.get(PEER_UID_XDATA, ""),
            xd.get("sym", sym_text),
            sym_height_mm=sym_h,
            block_name=ins.dxf.name,
            entity_type=str(t),
        )
        return
    if t in ("AND", "OR"):
        n = _gate_n_from_block(ins.dxf.name) or 2
        xd_gate = read_ld_app_dict(ins)
        show_stub_in_arrow = str(xd_gate.get(GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW) or "") == "1"
        win._props.show_gate(
            it.symbol_uid,
            sym_text,
            n,
            sym_visible,
            block_name=ins.dxf.name,
            entity_type=str(t),
            show_input_stub_in_arrow=show_stub_in_arrow,
        )
        return
    if t == ENTITY_TYPE_WIRE_BRANCH:
        win._props.show_wire_branch(it.symbol_uid)
        return
    if t == ENTITY_TYPE_CHECKPOINT:
        win._props.show_checkpoint(it.symbol_uid)
        return
    win._props.show_symbol(
        it.symbol_uid,
        sym_text,
        block_name=ins.dxf.name,
        entity_type=str(t or "SYMBOL"),
        sym_visible=sym_visible,
    )
