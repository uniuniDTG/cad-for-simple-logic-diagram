"""INSERT placement, ATTRIB, transforms."""

from __future__ import annotations

import re

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import Insert

from logic_cad.core.attrib_tags import is_supported_attdef_tag
from logic_cad.core.model.constants import (
    BLOCK_CHECKPOINT,
    BLOCK_INPAGE_FROM,
    BLOCK_INPAGE_TO,
    BLOCK_PAGE_FROM,
    BLOCK_PAGE_TO,
    BLOCK_WIRE_BRANCH,
    ENTITY_TYPE_CHECKPOINT,
    ENTITY_TYPE_INPAGE_REF,
    PAGE_REF_SHOW_PAGE_DESC_XDATA,
    PAGE_REF_SHOW_PAGE_NAME_XDATA,
    PAGE_REF_SHOW_TARGET_INFO_XDATA,
    ENTITY_TYPE_WIRE_BRANCH,
    INPAGE_SYM_HEIGHT_MM,
    INPAGE_SYM_HEIGHT_XDATA,
    GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW,
    PEER_UID_XDATA,
    SYMBOL_BLOCK_MAX_DIM_MM,
    TARGET_LAYOUT_XDATA,
)
from logic_cad.core.debug.debug_log import logic_cad_log
from logic_cad.core.services.dynamic_gate_factory import DynamicGateFactory, gate_view_geometry_from_block_name
from logic_cad.core.pages.inpage_ref import refresh_inpage_ref_syms_on_layout
from logic_cad.core.pages.page_ref import refresh_page_ref_syms_on_layout
from logic_cad.core.services.layout_service import (
    ensure_checkpoint_block,
    ensure_cross_page_reference_blocks,
    ensure_inpage_reference_blocks,
    ensure_wire_branch_block,
)
from logic_cad.core.symbol_clipboard import SymbolCopyRecord
from logic_cad.core.model.xdata import build_ld_app_tags, get_type, get_uid, new_uid, read_ld_app_dict, set_entity_xdata


def _page_ref_block_name(doc: Drawing, *, outgoing: bool) -> str:
    """outgoing: link on **source** page (PAGE_FROM). Else stub on **destination** (PAGE_TO)."""
    ensure_cross_page_reference_blocks(doc)
    return BLOCK_PAGE_FROM if outgoing else BLOCK_PAGE_TO


def _inpage_ref_block_name(*, outgoing: bool) -> str:
    """outgoing: ``●※n`` (INPAGE_FROM). Else ``※n●`` (INPAGE_TO)."""
    return BLOCK_INPAGE_FROM if outgoing else BLOCK_INPAGE_TO


def _uniform_scale_for_block(doc: Drawing, block_name: str) -> float:
    """Scale large CAD blocks (thousands of units) to ~SYMBOL_BLOCK_MAX_DIM_MM max side."""
    if block_name not in doc.blocks:
        return 1.0
    b = doc.blocks.get(block_name)
    try:
        from ezdxf import bbox

        e = bbox.extents(b)
    except Exception:
        return 1.0
    if e is None:
        return 1.0
    # ezdxf may set is_empty=True on BlockLayout even when size is valid; use size only.
    s = e.size
    mx = max(abs(float(s.x)), abs(float(s.y)), 1e-9)
    if mx < 1e-9:
        return 1.0
    if mx <= SYMBOL_BLOCK_MAX_DIM_MM:
        return 1.0
    return SYMBOL_BLOCK_MAX_DIM_MM / mx


def uniform_scale_for_block(doc: Drawing, block_name: str) -> float:
    """Public wrapper: uniform scale for INSERT preview / drag pixmap (same as placement)."""
    return _uniform_scale_for_block(doc, block_name)


class SymbolService:
    def __init__(self, doc: Drawing, gates: DynamicGateFactory) -> None:
        self.doc = doc
        self.gates = gates

    def _layout_block(self, layout_name: str):
        layout = self.doc.layouts.get(layout_name)
        return self.doc.blocks.get(layout.block_record_name)

    def _block_attdef(self, block_name: str, tag: str):
        if block_name not in self.doc.blocks:
            return None
        want = str(tag).upper()
        for ent in self.doc.blocks.get(block_name):
            if ent.dxftype() != "ATTDEF":
                continue
            if str(ent.dxf.tag).upper() == want:
                return ent
        return None

    def _block_has_attdef(self, block_name: str, tag: str) -> bool:
        return self._block_attdef(block_name, tag) is not None

    def _is_optional_symbol_tag(self, tag: str) -> bool:
        return is_supported_attdef_tag(tag)

    def _max_sym_suffix_on_layout(self, layout_name: str, pat: re.Pattern[str]) -> int:
        max_n = 0
        blk = self._layout_block(layout_name)
        for e in blk:
            if e.dxftype() != "INSERT":
                continue
            for a in e.attribs:
                if str(a.dxf.tag).upper() != "SYM":
                    continue
                m = pat.match(str(a.dxf.text or "").strip())
                if m:
                    max_n = max(max_n, int(m.group(1)))
        return max_n

    def next_sym_label(self, layout_name: str, block_name: str) -> str:
        """Next unused SYM text as {block_name}_{n} (e.g. RELAY_1). Also counts legacy {block_name}{n}."""
        prefix = block_name
        pat_new = re.compile("^" + re.escape(prefix) + r"_(\d+)$", re.IGNORECASE)
        pat_old = re.compile("^" + re.escape(prefix) + r"(\d+)$", re.IGNORECASE)
        max_n = max(
            self._max_sym_suffix_on_layout(layout_name, pat_new),
            self._max_sym_suffix_on_layout(layout_name, pat_old),
        )
        return f"{prefix}_{max_n + 1}"

    def next_gate_sym_label(self, layout_name: str, kind: str) -> str:
        """Next AND_n / OR_n on this layout (page-local sequence; independent of input pin count)."""
        k = str(kind).strip().upper()
        if k not in ("AND", "OR"):
            raise ValueError(f"ゲート種別は AND または OR である必要があります（{kind!r}）。")
        pat = re.compile("^" + re.escape(k) + r"_(\d+)$", re.IGNORECASE)
        max_n = self._max_sym_suffix_on_layout(layout_name, pat)
        return f"{k}_{max_n + 1}"

    def _fresh_sym_text_for_paste(self, layout_name: str, rec: SymbolCopyRecord) -> str:
        """SYM text for a newly pasted INSERT (same rules as place_* for each entity type)."""
        t = str(rec.entity_type or "SYMBOL").strip().upper()
        if t == "AND":
            return self.next_gate_sym_label(layout_name, "AND")
        if t == "OR":
            return self.next_gate_sym_label(layout_name, "OR")
        if t == ENTITY_TYPE_CHECKPOINT:
            return self.next_sym_label(layout_name, "CP")
        if t == ENTITY_TYPE_WIRE_BRANCH:
            return self.next_sym_label(layout_name, "BR")
        return self.next_sym_label(layout_name, rec.block_name)

    def _add_insert_attrib(self, ins: Insert, tag: str, value: str) -> bool:
        attdef = self._block_attdef(ins.dxf.name, tag)
        if attdef is None:
            return False
        loc = attdef.dxf.insert
        dxfattribs: dict = {"height": float(getattr(attdef.dxf, "height", 0.25) or 0.25)}
        if getattr(attdef.dxf, "rotation", None) is not None:
            dxfattribs["rotation"] = float(attdef.dxf.rotation)
        if getattr(attdef.dxf, "invisible", None) is not None:
            dxfattribs["invisible"] = int(attdef.dxf.invisible)
        ins.add_attrib(str(attdef.dxf.tag), value, (float(loc.x), float(loc.y)), dxfattribs=dxfattribs)
        return True

    def place_symbol(self, layout_name: str, block_name: str, pos: tuple[float, float], ref: str, entity_type: str) -> str:
        if block_name not in self.doc.blocks:
            raise ValueError(f"未定義のブロックです: {block_name!r}")
        blk = self._layout_block(layout_name)
        scale = _uniform_scale_for_block(self.doc, block_name)
        logic_cad_log(
            "symbol",
            f"place_symbol block={block_name!r} pos={pos} entity_type={entity_type!r} uniform_scale={scale}",
        )
        ins = blk.add_blockref(block_name, pos)
        if scale != 1.0:
            ins.dxf.xscale = scale
            ins.dxf.yscale = scale
            ins.dxf.zscale = scale
        uid = new_uid()
        tags = build_ld_app_tags("1", uid, entity_type)
        set_entity_xdata(ins, tags)
        if self._block_has_attdef(block_name, "SYM"):
            try:
                ins.add_auto_attribs({"SYM": ref})
            except ezdxf.DXFValueError:
                self._add_insert_attrib(ins, "SYM", ref)
            try:
                self.set_attrib_visible(layout_name, uid, "SYM", False)
            except ValueError:
                pass
        return uid

    def place_and_gate(self, layout_name: str, n_inputs: int, pos: tuple[float, float], ref: str | None = None) -> str:
        from logic_cad.core.model.constants import MIN_AND_OR_INPUTS

        n_inputs = max(MIN_AND_OR_INPUTS, int(n_inputs))
        name = self.gates.ensure_and_block(self.doc, n_inputs)
        if ref is None:
            ref = self.next_gate_sym_label(layout_name, "AND")
        return self.place_symbol(layout_name, name, pos, ref, "AND")

    def place_or_gate(self, layout_name: str, n_inputs: int, pos: tuple[float, float], ref: str | None = None) -> str:
        from logic_cad.core.model.constants import MIN_AND_OR_INPUTS

        n_inputs = max(MIN_AND_OR_INPUTS, int(n_inputs))
        name = self.gates.ensure_or_block(self.doc, n_inputs)
        if ref is None:
            ref = self.next_gate_sym_label(layout_name, "OR")
        return self.place_symbol(layout_name, name, pos, ref, "OR")

    def place_checkpoint(self, layout_name: str, pos: tuple[float, float], ref: str | None = None) -> str:
        ensure_checkpoint_block(self.doc)
        if BLOCK_CHECKPOINT not in self.doc.blocks:
            raise ValueError(f"未定義のブロックです: {BLOCK_CHECKPOINT!r}")
        if ref is None:
            ref = self.next_sym_label(layout_name, "CP")
        return self.place_symbol(layout_name, BLOCK_CHECKPOINT, pos, ref, ENTITY_TYPE_CHECKPOINT)

    def place_wire_branch(self, layout_name: str, pos: tuple[float, float], ref: str | None = None) -> str:
        ensure_wire_branch_block(self.doc)
        if BLOCK_WIRE_BRANCH not in self.doc.blocks:
            raise ValueError(f"未定義のブロックです: {BLOCK_WIRE_BRANCH!r}")
        if ref is None:
            ref = self.next_sym_label(layout_name, "BR")
        return self.place_symbol(layout_name, BLOCK_WIRE_BRANCH, pos, ref, ENTITY_TYPE_WIRE_BRANCH)

    def place_page_link(
        self,
        layout_name: str,
        pos: tuple[float, float],
        target_layout: str,
        pages: list[str],
        *,
        outgoing: bool = True,
    ) -> str:
        """*outgoing=True*: **source** page (PAGE_FROM → target). *outgoing=False*: **destination** page (PAGE_TO → back ref)."""
        _ = pages
        sym = ""
        bname = _page_ref_block_name(self.doc, outgoing=outgoing)
        scale = _uniform_scale_for_block(self.doc, bname)
        blk = self._layout_block(layout_name)
        ins = blk.add_blockref(bname, pos)
        if scale != 1.0:
            ins.dxf.xscale = scale
            ins.dxf.yscale = scale
            ins.dxf.zscale = scale
        uid = new_uid()
        tags = build_ld_app_tags(
            "1",
            uid,
            "PAGE_REF",
            {
                TARGET_LAYOUT_XDATA: target_layout,
                "sym": sym,
                PAGE_REF_SHOW_PAGE_NAME_XDATA: "0",
                PAGE_REF_SHOW_PAGE_DESC_XDATA: "0",
            },
        )
        set_entity_xdata(ins, tags)
        if self._block_has_attdef(bname, "SYM"):
            try:
                ins.add_auto_attribs({"SYM": sym})
            except ezdxf.DXFValueError:
                self._add_insert_attrib(ins, "SYM", sym)
            try:
                self.set_attrib_visible(layout_name, uid, "SYM", False)
            except ValueError:
                pass
        refresh_page_ref_syms_on_layout(self.doc, layout_name)
        return uid

    def _set_inpage_peer_xdata(self, layout_name: str, uid: str, peer_uid: str) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        prev = read_ld_app_dict(ins)
        uid_str = str(prev.get("uid") or get_uid(ins) or "")
        if not uid_str:
            raise ValueError("INSERT に uid がありません。")
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra[PEER_UID_XDATA] = peer_uid
        tags = build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra)
        set_entity_xdata(ins, tags)

    def place_inpage_ref(
        self,
        layout_name: str,
        pos: tuple[float, float],
        *,
        outgoing: bool = True,
        peer_uid: str = "",
    ) -> str:
        """Place one INPAGE_REF end (FROM or TO). *peer_uid* may be empty until the partner is placed."""
        ensure_inpage_reference_blocks(self.doc)
        sym = ""
        bname = _inpage_ref_block_name(outgoing=outgoing)
        scale = _uniform_scale_for_block(self.doc, bname)
        blk = self._layout_block(layout_name)
        ins = blk.add_blockref(bname, pos)
        if scale != 1.0:
            ins.dxf.xscale = scale
            ins.dxf.yscale = scale
            ins.dxf.zscale = scale
        uid = new_uid()
        h0 = float(INPAGE_SYM_HEIGHT_MM)
        tags = build_ld_app_tags(
            "1",
            uid,
            ENTITY_TYPE_INPAGE_REF,
            {
                PEER_UID_XDATA: peer_uid,
                "sym": sym,
                INPAGE_SYM_HEIGHT_XDATA: str(h0),
            },
        )
        set_entity_xdata(ins, tags)
        if self._block_has_attdef(bname, "SYM"):
            try:
                ins.add_auto_attribs({"SYM": sym})
            except ezdxf.DXFValueError:
                self._add_insert_attrib(ins, "SYM", sym)
            for a in ins.attribs:
                if str(a.dxf.tag).upper() == "SYM":
                    a.dxf.height = h0
                    break
        refresh_inpage_ref_syms_on_layout(self.doc, layout_name)
        return uid

    def set_inpage_sym_height(self, layout_name: str, uid: str, height_mm: float) -> None:
        """Set SYM text height (mm) for an INPAGE_REF INSERT; persists in LD_APP and ATTRIB."""
        h = max(0.25, min(80.0, float(height_mm)))
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        if get_type(ins) != ENTITY_TYPE_INPAGE_REF:
            raise ValueError("インページリンク（INPAGE_REF）ではありません。")
        prev = read_ld_app_dict(ins)
        uid_str = str(prev.get("uid") or get_uid(ins) or "")
        if not uid_str:
            raise ValueError("INSERT に uid がありません。")
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra[INPAGE_SYM_HEIGHT_XDATA] = str(h)
        tags = build_ld_app_tags("1", uid_str, ENTITY_TYPE_INPAGE_REF, extra)
        set_entity_xdata(ins, tags)
        for a in ins.attribs:
            if str(a.dxf.tag).upper() == "SYM":
                a.dxf.height = h
                return
        raise ValueError("SYM 属性がありません。")

    def link_inpage_ref_pair(self, layout_name: str, from_uid: str, to_uid: str) -> None:
        """Set mutual ``peer_uid`` on both INSERTs and renumber labels."""
        self._set_inpage_peer_xdata(layout_name, from_uid, to_uid)
        self._set_inpage_peer_xdata(layout_name, to_uid, from_uid)
        refresh_inpage_ref_syms_on_layout(self.doc, layout_name)

    def set_page_ref(self, layout_name: str, uid: str, target_layout: str, pages: list[str]) -> None:
        _ = pages
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        if get_type(ins) != "PAGE_REF":
            raise ValueError("ページ参照（PAGE_REF）ではありません。")
        prev = read_ld_app_dict(ins)
        uid_str = prev.get("uid") or get_uid(ins)
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra[TARGET_LAYOUT_XDATA] = target_layout
        extra["sym"] = prev.get("sym", "")
        tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
        set_entity_xdata(ins, tags)
        refresh_page_ref_syms_on_layout(self.doc, layout_name)

    def set_page_ref_target_info_visibility(
        self, layout_name: str, uid: str, *, show_page_name: bool, show_page_desc: bool
    ) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        if get_type(ins) != "PAGE_REF":
            raise ValueError("ページ参照（PAGE_REF）ではありません。")
        prev = read_ld_app_dict(ins)
        uid_str = prev.get("uid") or get_uid(ins)
        if not uid_str:
            raise ValueError("INSERT に uid がありません。")
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        extra.pop(PAGE_REF_SHOW_TARGET_INFO_XDATA, None)
        extra[PAGE_REF_SHOW_PAGE_NAME_XDATA] = "1" if show_page_name else "0"
        extra[PAGE_REF_SHOW_PAGE_DESC_XDATA] = "1" if show_page_desc else "0"
        tags = build_ld_app_tags("1", uid_str, "PAGE_REF", extra)
        set_entity_xdata(ins, tags)
        refresh_page_ref_syms_on_layout(self.doc, layout_name)

    def insert_by_uid(self, layout_name: str, uid: str) -> Insert | None:
        layout = self.doc.layouts.get(layout_name)
        blk = self.doc.blocks.get(layout.block_record_name)
        from logic_cad.core.model.xdata import get_uid

        for e in blk:
            if e.dxftype() == "INSERT" and get_uid(e) == uid:
                return e
        return None

    def set_symbol_attr(self, layout_name: str, uid: str, tag: str, value: str) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        for a in ins.attribs:
            if str(a.dxf.tag).upper() == str(tag).upper():
                a.dxf.text = value
                return
        block_name = ins.dxf.name
        if block_name not in self.doc.blocks:
            raise ValueError(f"属性タグ {tag!r} がありません。")
        if self._add_insert_attrib(ins, tag, value):
            return
        if self._is_optional_symbol_tag(tag):
            if not self._block_has_attdef(block_name, tag):
                return
            logic_cad_log(
                "symbol",
                f"set_symbol_attr: failed to add optional tag {tag!r} on block {block_name!r} (uid={uid})",
            )
            raise ValueError(f"属性 {tag!r} をブロック {block_name!r} に設定できません。")
        raise ValueError(f"属性タグ {tag!r} がありません。")

    def set_symbol_linetype(self, layout_name: str, uid: str, linetype: str) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        ins.dxf.linetype = linetype

    def set_symbol_text_visible(self, layout_name: str, uid: str, visible: bool) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        flag = 0 if visible else 1
        for a in ins.attribs:
            a.dxf.invisible = flag

    def set_attrib_visible(self, layout_name: str, uid: str, tag: str, visible: bool) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        for a in ins.attribs:
            if str(a.dxf.tag).upper() == str(tag).upper():
                a.dxf.invisible = 0 if visible else 1
                return
        if self._is_optional_symbol_tag(tag) and not self._block_has_attdef(ins.dxf.name, tag):
            return
        raise ValueError(f"属性タグ {tag!r} がありません。")

    def move_insert(self, layout_name: str, uid: str, pos: tuple[float, float]) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        if not ins.attribs:
            ins.dxf.insert = pos
            return
        prev = read_ld_app_dict(ins)
        uid_str = prev.get("uid") or get_uid(ins) or new_uid()
        t = get_type(ins) or "SYM"
        is_inpage = t == ENTITY_TYPE_INPAGE_REF
        attribs_state = [
            (str(a.dxf.tag), str(a.dxf.text or ""), int(getattr(a.dxf, "invisible", 0))) for a in ins.attribs
        ]
        bname = ins.dxf.name
        rot = float(ins.dxf.rotation)
        xs, ys = float(ins.dxf.xscale), float(ins.dxf.yscale)
        zs = float(ins.dxf.zscale)
        blk = self._layout_block(layout_name)
        for a in list(ins.attribs):
            self.doc.entitydb.delete_entity(a)
        self.doc.entitydb.delete_entity(ins)
        new_ins = blk.add_blockref(bname, pos)
        new_ins.dxf.rotation = rot
        new_ins.dxf.xscale = xs
        new_ins.dxf.yscale = ys
        new_ins.dxf.zscale = zs
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        tags = build_ld_app_tags("1", uid_str, t, extra)
        set_entity_xdata(new_ins, tags)
        seen_tag: set[str] = set()
        mapping: dict[str, str] = {}
        for tag, text, _inv in attribs_state:
            attdef = self._block_attdef(bname, tag)
            if attdef is None:
                continue
            canonical = str(attdef.dxf.tag)
            tu = canonical.upper()
            if tu in seen_tag:
                continue
            seen_tag.add(tu)
            mapping[canonical] = text
        if mapping:
            try:
                new_ins.add_auto_attribs(mapping)
            except Exception:
                for canonical, text in mapping.items():
                    try:
                        new_ins.add_auto_attribs({canonical: text})
                    except Exception:
                        self._add_insert_attrib(new_ins, canonical, text)
        for a in new_ins.attribs:
            for tag, _text, inv in attribs_state:
                if str(a.dxf.tag).upper() == str(tag).upper():
                    a.dxf.invisible = inv
                    break
        if is_inpage:
            refresh_inpage_ref_syms_on_layout(self.doc, layout_name)

    def rotate_insert_relative_deg(self, layout_name: str, uid: str, delta_degrees: float) -> None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        ins.dxf.rotation = float(ins.dxf.rotation) + float(delta_degrees)

    def change_gate_inputs(self, layout_name: str, uid: str, new_n: int) -> None:
        from logic_cad.core.model.constants import MIN_AND_OR_INPUTS

        if int(new_n) < MIN_AND_OR_INPUTS:
            raise ValueError(f"AND/OR ゲートには入力が少なくとも {MIN_AND_OR_INPUTS} 本必要です。")
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        from logic_cad.core.model.xdata import get_type, read_ld_app_dict

        t = get_type(ins)
        if t == "AND":
            new_block = self.gates.ensure_and_block(self.doc, new_n)
        elif t == "OR":
            new_block = self.gates.ensure_or_block(self.doc, new_n)
        else:
            raise ValueError("AND/OR ゲートではありません。")
        prev = read_ld_app_dict(ins)
        uid_str = prev.get("uid") or new_uid()
        attrib_vis = {a.dxf.tag: int(a.dxf.invisible) for a in ins.attribs}
        attribs = {a.dxf.tag: str(a.dxf.text or "") for a in ins.attribs}
        pos = (float(ins.dxf.insert.x), float(ins.dxf.insert.y))
        rot = float(ins.dxf.rotation)
        xs, ys = float(ins.dxf.xscale), float(ins.dxf.yscale)
        zs = float(ins.dxf.zscale)
        for a in list(ins.attribs):
            self.doc.entitydb.delete_entity(a)
        self.doc.entitydb.delete_entity(ins)
        blk = self._layout_block(layout_name)
        new_ins = blk.add_blockref(new_block, pos)
        new_ins.dxf.rotation = rot
        new_ins.dxf.xscale = xs
        new_ins.dxf.yscale = ys
        new_ins.dxf.zscale = zs
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        tags = build_ld_app_tags("1", uid_str, t or "AND", extra)
        set_entity_xdata(new_ins, tags)
        for tag, text in attribs.items():
            attdef = self._block_attdef(new_block, tag)
            if attdef is None:
                continue
            canonical = str(attdef.dxf.tag)
            try:
                new_ins.add_auto_attribs({canonical: str(text or "")})
            except Exception:
                self._add_insert_attrib(new_ins, canonical, str(text or ""))
        vis_by_u = {str(k).upper(): v for k, v in attrib_vis.items()}
        for a in new_ins.attribs:
            inv = vis_by_u.get(str(a.dxf.tag).upper())
            if inv is not None:
                a.dxf.invisible = inv

    def set_gate_show_input_stub_in_arrow(self, layout_name: str, uid: str, show: bool) -> None:
        """Persist stub-root arrow display on an AND/OR INSERT (Qt paint; same wing geometry as WIRE IN arrow).

        Args:
            layout_name: Active paper layout name.
            uid: INSERT uid (entity type AND or OR).
            show: Store ``show_input_stub_in_arrow`` in LD XDATA when True; remove when False.

        Returns:
            None

        Raises:
            ValueError: If the INSERT is missing or not an AND/OR gate.
        """
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            raise ValueError("INSERT が見つかりません。")
        t = get_type(ins)
        if t not in ("AND", "OR"):
            raise ValueError("AND/OR ゲートではありません。")
        prev = read_ld_app_dict(ins)
        uid_str = str(prev.get("uid") or get_uid(ins) or new_uid())
        ver = str(prev.get("ver") or "1")
        extra = {k: v for k, v in prev.items() if k not in ("ver", "uid", "type")}
        if show:
            extra[GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW] = "1"
        else:
            extra.pop(GATE_XDATA_SHOW_INPUT_STUB_IN_ARROW, None)
        tags = build_ld_app_tags(ver, uid_str, str(t), extra)
        set_entity_xdata(ins, tags)

    def clipboard_record_for_insert(self, layout_name: str, uid: str) -> SymbolCopyRecord | None:
        ins = self.insert_by_uid(layout_name, uid)
        if ins is None:
            return None
        d = read_ld_app_dict(ins)
        t = get_type(ins) or "SYMBOL"
        extra = {k: v for k, v in d.items() if k not in ("ver", "uid", "type")}
        attribs = [
            (str(a.dxf.tag), str(a.dxf.text or ""), int(getattr(a.dxf, "invisible", 0))) for a in ins.attribs
        ]
        return SymbolCopyRecord(
            source_uid=uid,
            block_name=str(ins.dxf.name),
            insert=(float(ins.dxf.insert.x), float(ins.dxf.insert.y)),
            rotation=float(ins.dxf.rotation),
            xscale=float(ins.dxf.xscale),
            yscale=float(ins.dxf.yscale),
            zscale=float(ins.dxf.zscale),
            entity_type=t,
            xdata_extra=extra,
            attribs=attribs,
        )

    def _ensure_dynamic_gate_block_for_paste(self, block_name: str) -> str | None:
        """Create AND_n/OR_n block definitions on demand (same as interactive placement).

        Clipboard paste can target a drawing that has never placed that gate size, so
        ``doc.blocks`` may not yet contain ``AND_2`` etc. Library import does not include
        these—DynamicGateFactory builds them per input count.

        Args:
            block_name: INSERT block name from clipboard (e.g. ``AND_2``).

        Returns:
            Canonical name now present in ``doc.blocks``, or ``None`` if *block_name* is
            not a dynamic AND/OR gate pattern.
        """

        if gate_view_geometry_from_block_name(block_name) is None:
            return None
        bu = str(block_name).strip().upper()
        kind, n_s = bu.split("_", 1)
        n_inputs = int(n_s)
        if kind == "AND":
            return self.gates.ensure_and_block(self.doc, n_inputs)
        if kind == "OR":
            return self.gates.ensure_or_block(self.doc, n_inputs)
        return None

    def paste_insert_from_clipboard(
        self, layout_name: str, rec: SymbolCopyRecord, pos: tuple[float, float]
    ) -> str:
        block_name = str(rec.block_name)
        if block_name not in self.doc.blocks:
            ensured = self._ensure_dynamic_gate_block_for_paste(block_name)
            if ensured is not None:
                block_name = ensured
        if block_name not in self.doc.blocks:
            raise ValueError(f"未定義のブロックです: {rec.block_name!r}")
        blk = self._layout_block(layout_name)
        ins = blk.add_blockref(block_name, pos)
        ins.dxf.rotation = float(rec.rotation)
        ins.dxf.xscale = float(rec.xscale)
        ins.dxf.yscale = float(rec.yscale)
        ins.dxf.zscale = float(rec.zscale)
        nu = new_uid()
        extra = dict(rec.xdata_extra)
        tags = build_ld_app_tags("1", nu, rec.entity_type, extra)
        set_entity_xdata(ins, tags)
        seen_tag: set[str] = set()
        for tag, text, inv in rec.attribs:
            attdef = self._block_attdef(block_name, tag)
            if attdef is None:
                continue
            canonical = str(attdef.dxf.tag)
            tu = canonical.upper()
            if tu in seen_tag:
                continue
            seen_tag.add(tu)
            try:
                ins.add_auto_attribs({canonical: text})
            except Exception:
                self._add_insert_attrib(ins, canonical, text)
        for a in ins.attribs:
            for tag, _text, inv in rec.attribs:
                if str(a.dxf.tag).upper() == str(tag).upper():
                    a.dxf.invisible = inv
                    break
        if get_type(ins) == "PAGE_REF":
            refresh_page_ref_syms_on_layout(self.doc, layout_name)
            return nu
        if get_type(ins) == ENTITY_TYPE_INPAGE_REF:
            return nu
        if self._block_has_attdef(block_name, "SYM"):
            try:
                self.set_symbol_attr(layout_name, nu, "SYM", self._fresh_sym_text_for_paste(layout_name, rec))
            except ValueError:
                logic_cad_log(
                    "symbol",
                    f"paste_insert_from_clipboard: could not set fresh SYM for uid={nu} block={block_name!r}",
                )
        return nu
