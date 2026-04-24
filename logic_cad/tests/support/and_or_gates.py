"""AND/OR gate block naming helpers for tests."""

from ezdxf.entities import Insert

from logic_cad.core.logic_diagram import LogicDiagram


def and_or_gate_input_count_from_insert(ins: Insert) -> int | None:
    """Parse input count ``n`` from ``AND_n`` / ``OR_n`` block reference name.

    Args:
        ins: Gate INSERT entity.

    Returns:
        ``n`` if the block name matches ``AND_*`` or ``OR_*`` with a numeric suffix,
        otherwise ``None``.
    """
    bn = str(ins.dxf.name).upper()
    if not (bn.startswith("AND_") or bn.startswith("OR_")):
        return None
    try:
        return int(bn.split("_", 1)[1])
    except ValueError:
        return None


def and_or_gate_input_count_for_symbol_uid(diagram: LogicDiagram, uid: str) -> int | None:
    """Input count for a placed AND/OR gate identified by symbol uid.

    Args:
        diagram: Active diagram.
        uid: Symbol instance uid.

    Returns:
        ``n`` from the block name, or ``None`` if the insert is missing or not AND/OR.
    """
    ins = diagram.symbols.insert_by_uid(diagram.current_layout_name, uid)
    if ins is None:
        return None
    return and_or_gate_input_count_from_insert(ins)
