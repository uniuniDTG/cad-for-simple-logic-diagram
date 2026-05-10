"""Tests for ``wire_port_helpers`` IN-port parsing aligned with ``parse_port_key``.

``_port_index`` and ``_vertical_lane_from_in_port`` delegate to ``parse_port_key``, which
normalizes case and surrounding whitespace — behavior is locked so refactors stay safe.
"""

from __future__ import annotations

from logic_cad.core.model.wire_port_helpers import _port_index, _vertical_lane_from_in_port


def test_port_index_canonical_logic_in() -> None:
    """Standard ``IN{k}_LOGIC`` keys map to numeric index."""

    assert _port_index("IN0_LOGIC") == 0
    assert _port_index("IN3_LOGIC") == 3


def test_port_index_strips_and_case_folds_like_parse_port_key() -> None:
    """Lowercase and padding are accepted the same way as :func:`parse_port_key`."""

    assert _port_index("  in1_logic ") == 1


def test_port_index_rejects_non_in_or_non_logic() -> None:
    """Outputs and VALUE/COM/etc. lanes are ignored for bundle helpers."""

    assert _port_index("OUT0_LOGIC") is None
    assert _port_index("IN0_VALUE") is None
    assert _port_index("garbage") is None


def test_vertical_lane_from_in_port_centering() -> None:
    """Lane offset matches ``index - (n_inputs-1)//2`` for LOGIC inputs."""

    # n=5 -> center index 2; IN2 lines up at lane 0
    assert _vertical_lane_from_in_port("IN2_LOGIC", 5) == 0
    assert _vertical_lane_from_in_port("IN0_LOGIC", 5) == -2
    assert _vertical_lane_from_in_port("OUT0_LOGIC", 5) == 0
