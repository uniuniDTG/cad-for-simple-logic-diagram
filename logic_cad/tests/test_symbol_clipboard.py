"""Copy/paste symbols with internal wires."""

import json

import pytest

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.xdata import get_type
from logic_cad.core.symbol_clipboard_codec import (
    decode_symbol_clipboard_payload_from_bytes,
    encode_symbol_clipboard_payload_to_bytes,
)


def _sym_text(d: LogicDiagram, uid: str) -> str:
    ins = d.symbols.insert_by_uid(d.current_layout_name, uid)
    assert ins is not None
    for a in ins.attribs:
        if str(a.dxf.tag).upper() == "SYM":
            return str(a.dxf.text or "")
    return str(ins.dxf.name)


def test_clipboard_payload_includes_internal_wire() -> None:
    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")
    d.rebuild_index()

    payload = d.build_symbol_clipboard_payload([u0, u1])
    assert len(payload.symbols) == 2
    assert len(payload.wires) == 1


def test_paste_clipboard_duplicates_symbols_and_wire() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")
    d.rebuild_index()

    payload = d.build_symbol_clipboard_payload([u0, u1])
    with d.begin("p"):
        pasted_syms, pasted_sk = d.paste_symbol_clipboard_payload(payload, (120.0, 55.0))
    assert len(pasted_syms) == 2
    assert not pasted_sk
    d.rebuild_index()

    blk = d.doc.blocks.get(d.doc.layouts.get(layout).block_record_name)
    n_wires = sum(1 for e in blk if e.dxftype() == "LWPOLYLINE" and get_type(e) == "WIRE")
    assert n_wires == 2
    n_not = sum(1 for e in blk if e.dxftype() == "INSERT" and str(e.dxf.name).upper() == "NOT")
    assert n_not == 4


def test_user_sketch_line_clipboard_paste() -> None:
    d = LogicDiagram.new()
    layout = d.current_layout_name
    with d.begin("a"):
        u = d.add_user_line((10.0, 20.0), (30.0, 20.0), "CONTINUOUS")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([], [u])
    assert not payload.symbols
    assert len(payload.user_sketches) == 1
    with d.begin("p"):
        syms, sks = d.paste_symbol_clipboard_payload(payload, (50.0, 50.0))
    assert not syms
    assert len(sks) == 1
    d.rebuild_index()
    blk = d.doc.blocks.get(d.doc.layouts.get(layout).block_record_name)
    n_lines = sum(
        1
        for e in blk
        if e.dxftype() == "LINE" and get_type(e) == "USER_LINE"
    )
    assert n_lines == 2


def test_paste_renumbers_sym_not_equal_to_source() -> None:
    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([u0])
    with d.begin("p"):
        pasted, _ = d.paste_symbol_clipboard_payload(payload, (100.0, 100.0))
    assert len(pasted) == 1
    d.rebuild_index()
    assert _sym_text(d, u0) == "n0"
    new_sym = _sym_text(d, pasted[0])
    assert new_sym != "n0"
    assert new_sym.upper().startswith("NOT_")


def test_paste_two_symbols_get_distinct_sym_labels() -> None:
    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([u0, u1])
    with d.begin("p"):
        pasted, _ = d.paste_symbol_clipboard_payload(payload, (120.0, 55.0))
    assert len(pasted) == 2
    d.rebuild_index()
    s0, s1 = _sym_text(d, pasted[0]), _sym_text(d, pasted[1])
    assert s0 != s1
    assert s0.upper().startswith("NOT_")
    assert s1.upper().startswith("NOT_")


def _count_wires_and_not_gates(d: LogicDiagram, layout_name: str) -> tuple[int, int]:
    blk = d.doc.blocks.get(d.doc.layouts.get(layout_name).block_record_name)
    n_wires = sum(1 for e in blk if e.dxftype() == "LWPOLYLINE" and get_type(e) == "WIRE")
    n_not = sum(1 for e in blk if e.dxftype() == "INSERT" and str(e.dxf.name).upper() == "NOT")
    return n_wires, n_not


def test_clipboard_codec_roundtrip_paste_matches_direct_payload() -> None:
    """Decoded clipboard bytes should paste the same as the in-memory payload."""

    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
        u1 = d.place_symbol("NOT", (60.0, 40.0), "n1")
    d.rebuild_index()
    with d.begin("w"):
        d.connect_ports(u0, "OUT0_LOGIC", u1, "IN0_LOGIC")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([u0, u1])
    blob = encode_symbol_clipboard_payload_to_bytes(payload)
    restored = decode_symbol_clipboard_payload_from_bytes(blob)

    d_direct = LogicDiagram.new()
    layout_a = d_direct.current_layout_name
    with d_direct.begin("p"):
        d_direct.paste_symbol_clipboard_payload(payload, (120.0, 55.0))

    d_via = LogicDiagram.new()
    layout_b = d_via.current_layout_name
    with d_via.begin("p"):
        d_via.paste_symbol_clipboard_payload(restored, (120.0, 55.0))

    wa, na = _count_wires_and_not_gates(d_direct, layout_a)
    wb, nb = _count_wires_and_not_gates(d_via, layout_b)
    assert wa == wb == 1
    assert na == nb == 2


def test_clipboard_codec_user_sketch_roundtrip() -> None:
    d = LogicDiagram.new()
    with d.begin("a"):
        u = d.add_user_line((10.0, 20.0), (30.0, 20.0), "CONTINUOUS")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([], [u])
    restored = decode_symbol_clipboard_payload_from_bytes(encode_symbol_clipboard_payload_to_bytes(payload))
    d2 = LogicDiagram.new()
    layout = d2.current_layout_name
    with d2.begin("p"):
        syms, sks = d2.paste_symbol_clipboard_payload(restored, (50.0, 50.0))
    assert not syms
    assert len(sks) == 1
    d2.rebuild_index()
    blk = d2.doc.blocks.get(d2.doc.layouts.get(layout).block_record_name)
    n_lines = sum(1 for e in blk if e.dxftype() == "LINE" and get_type(e) == "USER_LINE")
    assert n_lines == 1


def test_paste_and_gate_clipboard_ensures_dynamic_block() -> None:
    """Cross-doc paste must create AND_n blocks (they are not in the symbol library alone)."""

    src = LogicDiagram.new()
    with src.begin("a"):
        uid = src.place_and_gate(5, (20.0, 40.0))
    src.rebuild_index()
    payload = src.build_symbol_clipboard_payload([uid])

    dst = LogicDiagram.new()
    assert "AND_5" not in dst.doc.blocks
    with dst.begin("p"):
        pasted, _ = dst.paste_symbol_clipboard_payload(payload, (100.0, 100.0))
    assert len(pasted) == 1
    assert "AND_5" in dst.doc.blocks


def test_clipboard_codec_rejects_unsupported_version() -> None:
    d = LogicDiagram.new()
    with d.begin("a"):
        u0 = d.place_symbol("NOT", (20.0, 40.0), "n0")
    d.rebuild_index()
    payload = d.build_symbol_clipboard_payload([u0])
    root = json.loads(encode_symbol_clipboard_payload_to_bytes(payload).decode("utf-8"))
    root["v"] = 999
    bad = json.dumps(root).encode("utf-8")
    with pytest.raises(ValueError, match="Unsupported symbol clipboard version"):
        decode_symbol_clipboard_payload_from_bytes(bad)
