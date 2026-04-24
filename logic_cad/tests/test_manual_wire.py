"""Manual Manhattan wire path and skip_auto_reroute xdata."""

import pytest

from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.model.wire_port_helpers import wire_skips_auto_reroute

from logic_cad.tests.support.diagram_entities import ld_app_dict_for_uid, wire_polyline_points


def test_connect_ports_manual_sets_skip_flag_and_manhattan():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 14.0))
    d.rebuild_index()
    p0 = d.index.get_port_world(a, "OUT0_LOGIC")
    p1 = d.index.get_port_world(b, "IN0_LOGIC")
    assert p0 is not None and p1 is not None
    bends = [(24.0, p0[1]), (24.0, p1[1])]
    with d.begin("wire_manual"):
        wuid = d.connect_ports_manual(a, "OUT0_LOGIC", b, "IN0_LOGIC", bends)
    assert wire_skips_auto_reroute(ld_app_dict_for_uid(d.doc, wuid))
    pts = wire_polyline_points(d.doc, wuid)
    assert len(pts) >= 2
    for i in range(len(pts) - 1):
        a0, a1 = pts[i], pts[i + 1]
        assert abs(a0[0] - a1[0]) < 1e-6 or abs(a0[1] - a1[1]) < 1e-6


def test_connect_ports_auto_trims_tiny_terminal_backtrack(monkeypatch) -> None:
    """Auto-route output with tiny overshoot at dst is normalized to exact endpoints."""
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 40.0), "DST")
    d.rebuild_index()
    p0 = d.index.get_port_world(src, "OUT0_LOGIC")
    p1 = d.index.get_port_world(dst, "IN0_LOGIC")
    assert p0 is not None and p1 is not None

    def _fake_auto_route(*_args, **_kwargs):
        return [p0, (p1[0] + 0.135, p1[1])]

    monkeypatch.setattr(d.wires, "_auto_route_manhattan_interior_points", _fake_auto_route)
    with d.begin("wire-auto"):
        wuid = d.connect_ports(src, "OUT0_LOGIC", dst, "IN0_LOGIC")
    pts = wire_polyline_points(d.doc, wuid)
    assert pts[0] == pytest.approx(p0)
    assert pts[-1] == pytest.approx(p1)
    assert len(pts) == 2


def test_parallel_move_translates_and_input_bundle_polylines():
    d = LogicDiagram.new()
    with d.begin("place"):
        s0 = d.place_symbol("NOT", (10.0, 20.0), "N0")
        s1 = d.place_symbol("NOT", (10.0, 36.0), "N1")
        g = d.place_and_gate(2, (48.0, 28.0))
    with d.begin("w0"):
        d.connect_ports(s0, "OUT0_LOGIC", g, "IN0_LOGIC")
    with d.begin("w1"):
        d.connect_ports(s1, "OUT0_LOGIC", g, "IN1_LOGIC")
    d.rebuild_index()
    metas = list(d.wires.iter_wire_meta(d.current_layout_name))
    assert len(metas) == 2
    before = {wu: d.wires._polyline_points(e) for e, wu, _ in metas}
    dx, dy = -4.0, 0.0
    with d.begin("move-all"):
        d.symbols.move_insert(d.current_layout_name, s0, (6.0, 20.0))
        d.symbols.move_insert(d.current_layout_name, s1, (6.0, 36.0))
        d.symbols.move_insert(d.current_layout_name, g, (44.0, 28.0))
        d.rebuild_index()
        assert d.wires.reroute_wires_touching(
            d.index,
            d.current_layout_name,
            {s0, s1, g},
            symbol_move_deltas={s0: (dx, dy), s1: (dx, dy), g: (dx, dy)},
        )
    for e, wu, _ in d.wires.iter_wire_meta(d.current_layout_name):
        after = d.wires._polyline_points(e)
        b = before[wu]
        assert len(after) == len(b)
        for (x0, y0), (x1, y1) in zip(b, after):
            assert abs((x1 - x0) - dx) < 1e-5 and abs((y1 - y0) - dy) < 1e-5


def test_parallel_move_translates_auto_wire_polyline():
    """Both endpoints selected with the same delta: translate path, no new Manhattan search."""
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_symbol("NOT", (20.0, 40.0), "NA")
        b = d.place_symbol("NOT", (60.0, 40.0), "NB")
    with d.begin("wire-nn"):
        d.connect_ports(a, "OUT0_LOGIC", b, "IN0_LOGIC")
    d.rebuild_index()
    e0, wuid, _ = next(iter(d.wires.iter_wire_meta(d.current_layout_name)))
    before = d.wires._polyline_points(e0)
    dx, dy = 8.0, 0.0
    with d.begin("move-both"):
        d.symbols.move_insert(d.current_layout_name, a, (28.0, 40.0))
        d.symbols.move_insert(d.current_layout_name, b, (68.0, 40.0))
        d.rebuild_index()
        assert d.wires.reroute_wires_touching(
            d.index,
            d.current_layout_name,
            {a, b},
            symbol_move_deltas={a: (dx, dy), b: (dx, dy)},
        )
    e1 = find_entity_by_uid(d.doc, wuid)
    assert e1 is not None
    after = d.wires._polyline_points(e1)
    assert len(after) == len(before)
    for (x0, y0), (x1, y1) in zip(before, after):
        assert abs((x1 - x0) - dx) < 1e-5 and abs((y1 - y0) - dy) < 1e-5


def test_parallel_move_normalizes_tiny_terminal_backtrack() -> None:
    """Parallel-translation reroute also removes pre-existing tiny endpoint reversals."""
    d = LogicDiagram.new()
    with d.begin("place"):
        src = d.place_symbol("NOT", (20.0, 40.0), "SRC")
        dst = d.place_symbol("NOT", (60.0, 40.0), "DST")
    with d.begin("wire"):
        wuid = d.connect_ports(src, "OUT0_LOGIC", dst, "IN0_LOGIC")
    d.rebuild_index()
    e = find_entity_by_uid(d.doc, wuid)
    assert e is not None
    p0 = d.index.get_port_world(src, "OUT0_LOGIC")
    p1 = d.index.get_port_world(dst, "IN0_LOGIC")
    assert p0 is not None and p1 is not None
    with d.begin("inject-backtrack"):
        d.wires.set_wire_points(
            d.current_layout_name,
            e,
            [p0, (p1[0] + 0.135, p1[1]), p1],
            snap_branches=False,
        )
    dx, dy = 8.0, 0.0
    with d.begin("move"):
        d.symbols.move_insert(d.current_layout_name, src, (28.0, 40.0))
        d.symbols.move_insert(d.current_layout_name, dst, (68.0, 40.0))
        d.rebuild_index()
        assert d.wires.reroute_wires_touching(
            d.index,
            d.current_layout_name,
            {src, dst},
            symbol_move_deltas={src: (dx, dy), dst: (dx, dy)},
        )
    d.rebuild_index()
    p0_after = d.index.get_port_world(src, "OUT0_LOGIC")
    p1_after = d.index.get_port_world(dst, "IN0_LOGIC")
    assert p0_after is not None and p1_after is not None
    pts = wire_polyline_points(d.doc, wuid)
    assert pts[0] == pytest.approx(p0_after)
    assert pts[-1] == pytest.approx(p1_after)
    assert len(pts) == 2


def test_manual_wire_reroutes_after_symbol_move():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (40.0, 14.0))
    d.rebuild_index()
    p0 = d.index.get_port_world(a, "OUT0_LOGIC")
    p1 = d.index.get_port_world(b, "IN0_LOGIC")
    assert p0 is not None and p1 is not None
    bends = [(24.0, p0[1]), (24.0, p1[1])]
    with d.begin("wire_manual"):
        wuid = d.connect_ports_manual(a, "OUT0_LOGIC", b, "IN0_LOGIC", bends)
    before = wire_polyline_points(d.doc, wuid)
    with d.begin("move"):
        d.symbols.move_insert(d.current_layout_name, a, (12.0, 10.0))
        assert d.reroute_wires_after_symbol_moves({a})
    after = wire_polyline_points(d.doc, wuid)
    assert after != before
    d.rebuild_index()
    p0n = d.index.get_port_world(a, "OUT0_LOGIC")
    p1n = d.index.get_port_world(b, "IN0_LOGIC")
    assert p0n is not None and p1n is not None
    assert abs(after[0][0] - p0n[0]) < 0.02 and abs(after[0][1] - p0n[1]) < 0.02
    assert abs(after[-1][0] - p1n[0]) < 0.02 and abs(after[-1][1] - p1n[1]) < 0.02


def test_connect_ports_manual_rejects_diagonal_segment():
    d = LogicDiagram.new()
    with d.begin("place"):
        a = d.place_and_gate(1, (10.0, 10.0))
        b = d.place_and_gate(1, (30.0, 20.0))
    d.rebuild_index()
    p0 = d.index.get_port_world(a, "OUT0_LOGIC")
    assert p0 is not None
    bends = [(25.0, 18.0)]
    try:
        with d.begin("bad"):
            d.connect_ports_manual(a, "OUT0_LOGIC", b, "IN0_LOGIC", bends)
    except ValueError as ex:
        assert "マンハッタン" in str(ex) or "Manhattan" in str(ex)
    else:
        raise AssertionError("expected ValueError")
