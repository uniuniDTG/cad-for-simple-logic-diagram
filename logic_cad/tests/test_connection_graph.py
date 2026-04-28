"""Port compatibility and unit resolution."""

from logic_cad.core.model.connection_graph import ports_compatible, resolve_wire_unit


def test_logic_value_now_compatible() -> None:
    assert ports_compatible("LOGIC", "VALUE")


def test_multi_with_logic() -> None:
    assert ports_compatible("MULTI", "VALUE")
    assert resolve_wire_unit("MULTI", "VALUE") == "VALUE"


def test_com_is_compatible_with_all_units() -> None:
    assert ports_compatible("COM", "LOGIC")
    assert ports_compatible("COM", "VALUE")
    assert ports_compatible("COM", "MULTI")
    assert ports_compatible("COM", "COM")


def test_resolve_wire_unit_prioritizes_com() -> None:
    assert resolve_wire_unit("COM", "LOGIC") == "COM"
    assert resolve_wire_unit("MULTI", "COM") == "COM"
