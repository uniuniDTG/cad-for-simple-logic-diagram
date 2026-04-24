"""Layers for USER_LINE / USER_CIRCLE / USER_CLOUD sketch entities."""

from __future__ import annotations

from ezdxf.entities import DXFEntity

from logic_cad.core.model.constants import (
    LAYER_ANNOTATION,
    LAYER_USER_CIRCLE_CENTER,
    LAYER_USER_CIRCLE_CONTINUOUS,
    LAYER_USER_CIRCLE_DASHED,
    LAYER_USER_CLOUD_CENTER,
    LAYER_USER_CLOUD_CONTINUOUS,
    LAYER_USER_CLOUD_DASHED,
    LAYER_USER_LINE_CENTER,
    LAYER_USER_LINE_CONTINUOUS,
    LAYER_USER_LINE_DASHED,
    LINETYPE_CENTER,
    LINETYPE_CONTINUOUS,
    LINETYPE_DASH,
    LINETYPE_VALUE,
)

USER_SKETCH_WIRE_LAYERS: frozenset[str] = frozenset(
    {
        LAYER_USER_LINE_CONTINUOUS,
        LAYER_USER_LINE_CENTER,
        LAYER_USER_LINE_DASHED,
        LAYER_USER_CIRCLE_CONTINUOUS,
        LAYER_USER_CIRCLE_CENTER,
        LAYER_USER_CIRCLE_DASHED,
        LAYER_USER_CLOUD_CONTINUOUS,
        LAYER_USER_CLOUD_CENTER,
        LAYER_USER_CLOUD_DASHED,
    }
)

# Layer name -> UI combo value (CONTINUOUS / DASHED / CENTER)
_LAYER_TO_DISPLAY_LINETYPE: dict[str, str] = {
    LAYER_USER_LINE_CONTINUOUS: "CONTINUOUS",
    LAYER_USER_LINE_CENTER: "CENTER",
    LAYER_USER_LINE_DASHED: "DASHED",
    LAYER_USER_CIRCLE_CONTINUOUS: "CONTINUOUS",
    LAYER_USER_CIRCLE_CENTER: "CENTER",
    LAYER_USER_CIRCLE_DASHED: "DASHED",
    LAYER_USER_CLOUD_CONTINUOUS: "CONTINUOUS",
    LAYER_USER_CLOUD_CENTER: "CENTER",
    LAYER_USER_CLOUD_DASHED: "DASHED",
}


def is_user_sketch_wire_layer(name: str) -> bool:
    """Return True if *name* is a layer used for USER sketch entities.

    Args:
        name: Layer name from an entity.

    Returns:
        True when *name* is one of the USER sketch linetype layers.
    """
    return str(name) in USER_SKETCH_WIRE_LAYERS


def normalize_user_sketch_linetype(linetype: str) -> str:
    """Normalize UI/DXF linetype strings to ``CONTINUOUS``, ``DASHED``, or ``CENTER``.

    Uses user-aux constants only — not ``LINETYPE_LOGIC``, so Logic-wire defaults can change
    independently (e.g. Logic linetype set to dashed).

    Args:
        linetype: Raw name (e.g. ``LINETYPE_CONTINUOUS``, ``DASHED``, ``LINETYPE_VALUE``).

    Returns:
        One of ``CONTINUOUS``, ``DASHED``, ``CENTER``.
    """
    s = str(linetype or "").strip().upper()
    if s in (LINETYPE_DASH.upper(), LINETYPE_VALUE.upper(), "DASHED"):
        return "DASHED"
    if s in (LINETYPE_CENTER.upper(), "CENTER"):
        return "CENTER"
    if s in ("", LINETYPE_CONTINUOUS.upper(), "CONTINUOUS"):
        return "CONTINUOUS"
    return "CONTINUOUS"


def user_sketch_line_layer_for_linetype(linetype: str) -> str:
    """Map sketch linetype to the LINE layer (BYLAYER inherits that layer's default linetype).

    Args:
        linetype: UI or DXF linetype name.

    Returns:
        ``LAYER_USER_LINE_*`` for CONTINUOUS / CENTER / DASHED.
    """
    key = normalize_user_sketch_linetype(linetype)
    if key == "DASHED":
        return LAYER_USER_LINE_DASHED
    if key == "CENTER":
        return LAYER_USER_LINE_CENTER
    return LAYER_USER_LINE_CONTINUOUS


def user_sketch_circle_layer_for_linetype(linetype: str) -> str:
    """Map sketch linetype to the CIRCLE layer (BYLAYER inherits that layer's default linetype).

    Args:
        linetype: UI or DXF linetype name.

    Returns:
        ``LAYER_USER_CIRCLE_*`` for CONTINUOUS / CENTER / DASHED.
    """
    key = normalize_user_sketch_linetype(linetype)
    if key == "DASHED":
        return LAYER_USER_CIRCLE_DASHED
    if key == "CENTER":
        return LAYER_USER_CIRCLE_CENTER
    return LAYER_USER_CIRCLE_CONTINUOUS


def user_sketch_cloud_layer_for_linetype(linetype: str) -> str:
    """Map sketch linetype to the CLOUD layer (BYLAYER inherits that layer's default linetype).

    Args:
        linetype: UI or DXF linetype name.

    Returns:
        ``LAYER_USER_CLOUD_*`` for CONTINUOUS / CENTER / DASHED.
    """
    key = normalize_user_sketch_linetype(linetype)
    if key == "DASHED":
        return LAYER_USER_CLOUD_DASHED
    if key == "CENTER":
        return LAYER_USER_CLOUD_CENTER
    return LAYER_USER_CLOUD_CONTINUOUS


def user_sketch_entity_linetype_for_display(linetype: str) -> str:
    """Return the explicit DXF linetype name to store on USER_LINE / USER_CIRCLE.

    Args:
        linetype: UI or DXF linetype name.

    Returns:
        Normalized explicit DXF linetype name (``CONTINUOUS``, ``DASHED``, ``CENTER``).
    """
    return normalize_user_sketch_linetype(linetype)


def user_sketch_display_linetype_for_entity(entity: DXFEntity) -> str:
    """Resolve linetype string for the property combo (CONTINUOUS / DASHED / CENTER).

    Sketch entities use ``ByLayer`` on a dedicated USER sketch layer; explicit non-ByLayer
    linetypes are returned as-is when present.

    Args:
        entity: A LINE or CIRCLE with USER_LINE / USER_CIRCLE XDATA.

    Returns:
        ``CONTINUOUS``, ``DASHED``, or ``CENTER`` (or a non-ByLayer name if set).
    """
    lt_raw = getattr(entity.dxf, "linetype", None)
    s = str(lt_raw).strip() if lt_raw else ""
    if s and s.upper() not in ("BYLAYER", "BYBLOCK"):
        return normalize_user_sketch_linetype(s)
    lyr = str(entity.dxf.layer)
    if lyr in _LAYER_TO_DISPLAY_LINETYPE:
        return _LAYER_TO_DISPLAY_LINETYPE[lyr]
    if lyr == LAYER_ANNOTATION:
        return "CONTINUOUS"
    return "CONTINUOUS"
