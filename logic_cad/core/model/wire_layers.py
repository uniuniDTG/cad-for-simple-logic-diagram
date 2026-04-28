"""Wire routing layer names and helpers.

Logic CAD stores WIRE ``LWPOLYLINE`` entities on ``LD_WIRE_LOGIC``, ``LD_WIRE_VALUE``,
or ``LD_WIRE_COM`` depending on XDATA ``unit`` (LOGIC / VALUE / COM). Use
:func:`layer_for_wire_unit` when
creating geometry and :func:`is_wire_layer` when scanning layout blocks.
"""

from __future__ import annotations

from logic_cad.core.model.constants import LAYER_WIRE_COM, LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE

WIRE_LAYERS: frozenset[str] = frozenset({LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE, LAYER_WIRE_COM})


def is_wire_layer(name: str) -> bool:
    """Return True if *name* is a layer used for WIRE / WIRE_ARROW LWPOLYLINE entities."""
    return str(name) in WIRE_LAYERS


def layer_for_wire_unit(wunit: str) -> str:
    """Return the DXF layer name for WIRE geometry from XDATA ``unit``.

    Args:
        wunit: Wire unit string (case-insensitive), e.g. ``LOGIC``, ``VALUE``, ``COM``.

    Returns:
        ``LAYER_WIRE_LOGIC``, ``LAYER_WIRE_VALUE``, or ``LAYER_WIRE_COM``.

    Raises:
        ValueError: If *wunit* is not ``LOGIC``, ``VALUE``, or ``COM``.
    """
    u = str(wunit).upper().strip()
    if u == "LOGIC":
        return LAYER_WIRE_LOGIC
    if u == "VALUE":
        return LAYER_WIRE_VALUE
    if u == "COM":
        return LAYER_WIRE_COM
    raise ValueError(f"wire unit must be LOGIC, VALUE, or COM, got {wunit!r}")
