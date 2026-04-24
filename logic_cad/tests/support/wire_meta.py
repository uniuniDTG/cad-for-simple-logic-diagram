"""Wire metadata iteration helpers for tests."""

from logic_cad.core.logic_diagram import LogicDiagram


def wire_meta_dicts_for_layout(diagram: LogicDiagram, layout_name: str) -> list[dict]:
    """Return a snapshot list of wire metadata dicts (copies) for a layout.

    Args:
        diagram: Active diagram.
        layout_name: Layout name passed to ``iter_wire_meta``.

    Returns:
        List of copied metadata dicts (safe if callers mutate entries).
    """
    return [dict(m) for _e, _wu, m in diagram.wires.iter_wire_meta(layout_name)]


def count_wires_in_layout(diagram: LogicDiagram, layout_name: str) -> int:
    """Count wire entities reported by ``iter_wire_meta`` for a layout.

    Args:
        diagram: Active diagram.
        layout_name: Layout name passed to ``iter_wire_meta``.

    Returns:
        Number of wire rows.
    """
    return sum(1 for _e, _wu, _m in diagram.wires.iter_wire_meta(layout_name))


def count_wires_to_dst_port(
    diagram: LogicDiagram,
    layout_name: str,
    dst_uid: str,
    dst_port: str,
) -> int:
    """Count wires whose meta reports the given destination uid and port.

    Args:
        diagram: Active diagram.
        layout_name: Paper/layout name passed to ``iter_wire_meta``.
        dst_uid: Destination endpoint uid.
        dst_port: Destination port name (e.g. ``IN0_MULTI``).

    Returns:
        Number of matching wire rows.
    """
    return sum(
        1
        for _e, _wu, meta in diagram.wires.iter_wire_meta(layout_name)
        if meta.get("dst") == dst_uid and str(meta.get("dst_port") or "") == dst_port
    )


def wire_entity_meta_rows_to_dst(
    diagram: LogicDiagram, dst_uid: str
) -> list[tuple[object, dict]]:
    """Collect ``(entity, meta)`` for wires whose metadata ``dst`` is ``dst_uid``.

    Args:
        diagram: Active diagram.
        dst_uid: Destination symbol uid (e.g. AND gate).

    Returns:
        List of pairs from ``iter_wire_meta`` matching the destination.
    """
    rows: list[tuple[object, dict]] = []
    for entity, _wu, data in diagram.wires.iter_wire_meta(diagram.current_layout_name):
        if data.get("dst") == dst_uid:
            rows.append((entity, data))
    return rows


def wire_entity_meta_rows_all(diagram: LogicDiagram) -> list[tuple[object, dict]]:
    """All ``(entity, meta)`` pairs for the current layout.

    Args:
        diagram: Active diagram.

    Returns:
        List of ``(entity, wire metadata dict)`` for every wire row.
    """
    rows: list[tuple[object, dict]] = []
    for entity, _wu, data in diagram.wires.iter_wire_meta(diagram.current_layout_name):
        rows.append((entity, data))
    return rows


def count_wires_from_src_port(
    diagram: LogicDiagram,
    layout_name: str,
    src_uid: str,
    src_port: str,
) -> int:
    """Count wires whose meta reports the given source uid and port.

    Args:
        diagram: Active diagram.
        layout_name: Paper/layout name passed to ``iter_wire_meta``.
        src_uid: Source endpoint uid (e.g. WIRE_BRANCH insert).
        src_port: Source port name (e.g. ``OUT0_MULTI``).

    Returns:
        Number of matching wire rows.
    """
    return sum(
        1
        for _e, _wu, meta in diagram.wires.iter_wire_meta(layout_name)
        if meta.get("src") == src_uid and meta.get("src_port") == src_port
    )


def assert_wire_meta_canonical_out_to_in(meta: dict) -> None:
    """Assert wire meta uses OUT* source and IN* destination (canonical orientation).

    Args:
        meta: Wire metadata dict from ``iter_wire_meta``.

    Raises:
        AssertionError: If ports are not OUT*/IN* as expected.
    """
    sp = str(meta.get("src_port") or "").upper()
    dp = str(meta.get("dst_port") or "").upper()
    assert sp.startswith("OUT"), meta
    assert dp.startswith("IN"), meta
