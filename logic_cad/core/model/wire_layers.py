"""Wire routing layer names and helpers.

Logic CAD stores WIRE ``LWPOLYLINE`` entities on ``LD_WIRE_LOGIC`` or ``LD_WIRE_VALUE``
depending on XDATA ``unit`` (LOGIC vs VALUE). Use :func:`layer_for_wire_unit` when
creating geometry and :func:`is_wire_layer` when scanning layout blocks.
"""

from __future__ import annotations

from logic_cad.core.model.constants import LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE

WIRE_LAYERS: frozenset[str] = frozenset({LAYER_WIRE_LOGIC, LAYER_WIRE_VALUE})


def is_wire_layer(name: str) -> bool:
    """Return True if *name* is a layer used for WIRE / WIRE_ARROW LWPOLYLINE entities."""
    return str(name) in WIRE_LAYERS


def layer_for_wire_unit(wunit: str) -> str:
    """Return the DXF layer name for WIRE geometry from XDATA ``unit`` (LOGIC or VALUE).

    Args:
        wunit: Wire unit string (case-insensitive), e.g. ``LOGIC`` or ``VALUE``.

    Returns:
        ``LAYER_WIRE_LOGIC`` or ``LAYER_WIRE_VALUE``.

    Raises:
        ValueError: If *wunit* is not ``LOGIC`` or ``VALUE``.
    """
    u = str(wunit).upper().strip()
    if u == "LOGIC":
        return LAYER_WIRE_LOGIC
    if u == "VALUE":
        return LAYER_WIRE_VALUE
    raise ValueError(f"wire unit must be LOGIC or VALUE, got {wunit!r}")
