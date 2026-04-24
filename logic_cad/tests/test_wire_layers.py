"""Unit tests for wire layer helpers."""

from __future__ import annotations

import pytest

from logic_cad.core.model.constants import LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE
from logic_cad.core.model.wire_layers import WIRE_LAYERS, is_wire_layer, layer_for_wire_unit


def test_wire_layers_contains_both_constants() -> None:
    """WIRE_LAYERS lists exactly the two routing layers."""
    assert WIRE_LAYERS == frozenset({LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE})


def test_is_wire_layer_true_for_logic_and_value() -> None:
    """is_wire_layer accepts layer names used for WIRE geometry."""
    assert is_wire_layer(LAYER_WIRE_LOGIC) is True
    assert is_wire_layer(LAYER_WIRE_VALUE) is True


def test_is_wire_layer_false_for_other_layers() -> None:
    """Non-wire layers are not classified as wire layers."""
    assert is_wire_layer("LD_SYMBOL") is False
    assert is_wire_layer("LD_WIRE_BRIDGE") is False


def test_layer_for_wire_unit_logic_and_value() -> None:
    """layer_for_wire_unit maps LOGIC / VALUE (case-insensitive)."""
    assert layer_for_wire_unit("LOGIC") == LAYER_WIRE_LOGIC
    assert layer_for_wire_unit("logic") == LAYER_WIRE_LOGIC
    assert layer_for_wire_unit("VALUE") == LAYER_WIRE_VALUE


def test_layer_for_wire_unit_invalid_raises() -> None:
    """Unknown units raise ValueError."""
    with pytest.raises(ValueError):
        layer_for_wire_unit("MULTI")
