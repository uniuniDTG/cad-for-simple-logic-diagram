"""Port key parsing helpers for LD_PORT conventions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

PortDirection = Literal["IN", "OUT", "INOUT"]
PortUnit = Literal["LOGIC", "VALUE", "MULTI", "COM"]

_PORT_KEY_RE = re.compile(r"^(INOUT|IN|OUT)(\d+)_(LOGIC|VALUE|MULTI|COM)$")
_PORT_LAYER_RE = re.compile(r"^LD_PORT_(INOUT|IN|OUT)(\d+)_(LOGIC|VALUE|MULTI|COM)$")


@dataclass(frozen=True)
class PortKey:
    """Structured representation of a parsed port key.

    Args:
        direction: Port direction token (`IN`, `OUT`, `INOUT`).
        index: Numeric index in the key.
        unit: Port electrical/logical unit token.
    """

    direction: PortDirection
    index: int
    unit: PortUnit


def parse_port_key(port_key: str) -> PortKey | None:
    """Parse `IN0_LOGIC` / `OUT0_MULTI` / `INOUT1_COM` style keys.

    Args:
        port_key: Raw port key string.

    Returns:
        Parsed :class:`PortKey` when valid, otherwise ``None``.
    """

    key = str(port_key or "").strip().upper()
    match = _PORT_KEY_RE.fullmatch(key)
    if match is None:
        return None
    direction, idx_s, unit = match.groups()
    return PortKey(direction=direction, index=int(idx_s), unit=unit)


def format_port_layer(pk: PortKey) -> str:
    """Build ``LD_PORT_IN0_LOGIC`` style layer name from a :class:`PortKey`."""

    return f"LD_PORT_{pk.direction}{pk.index}_{pk.unit}"


def parse_port_layer(layer_name: str) -> PortKey | None:
    """Parse `LD_PORT_*` layer names into a :class:`PortKey`.

    Args:
        layer_name: DXF layer name.

    Returns:
        Parsed :class:`PortKey` when valid, otherwise ``None``.
    """

    layer = str(layer_name or "").strip().upper()
    match = _PORT_LAYER_RE.fullmatch(layer)
    if match is None:
        return None
    direction, idx_s, unit = match.groups()
    return PortKey(direction=direction, index=int(idx_s), unit=unit)


def is_input_port_key(port_key: str) -> bool:
    """Return True only for pure `IN*` keys (not `INOUT*`)."""

    parsed = parse_port_key(port_key)
    return bool(parsed is not None and parsed.direction == "IN")


def is_output_port_key(port_key: str) -> bool:
    """Return True only for pure `OUT*` keys (not `INOUT*`)."""

    parsed = parse_port_key(port_key)
    return bool(parsed is not None and parsed.direction == "OUT")


def is_inout_port_key(port_key: str) -> bool:
    """Return True for `INOUT*` keys."""

    parsed = parse_port_key(port_key)
    return bool(parsed is not None and parsed.direction == "INOUT")
