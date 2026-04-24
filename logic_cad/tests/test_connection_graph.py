"""Port compatibility."""

from logic_cad.core.model.connection_graph import ports_compatible, resolve_wire_unit


def test_logic_value_incompatible():
    assert not ports_compatible("LOGIC", "VALUE")


def test_multi_with_logic():
    assert ports_compatible("MULTI", "VALUE")
    assert resolve_wire_unit("MULTI", "VALUE") == "VALUE"
