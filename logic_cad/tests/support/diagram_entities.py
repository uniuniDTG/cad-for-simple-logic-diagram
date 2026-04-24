"""Entity lookup and geometry extraction helpers for tests."""

from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity

from logic_cad.core.model.xdata import read_ld_app_dict
from logic_cad.core.undo.history import find_entity_by_uid


def ld_app_dict_for_uid(doc: Drawing, uid: str) -> dict[str, str]:
    """Resolve an entity by LD_APP uid and return its LD_APP key-value map.

    Args:
        doc: Drawing to search.
        uid: Logical entity uid stored in XDATA.

    Returns:
        Parsed LD_APP dictionary (empty if no XDATA).

    Raises:
        AssertionError: If no entity exists for ``uid``.
    """
    ent = find_entity_by_uid(doc, uid)
    assert ent is not None, f"no entity for uid {uid!r}"
    return read_ld_app_dict(ent)


def entity_and_ld_app_dict_for_uid(doc: Drawing, uid: str) -> tuple[DXFEntity, dict[str, str]]:
    """Resolve entity by uid and return both the entity and LD_APP map (single lookup).

    Use this when tests must both mutate the entity (XDATA) and read metadata.

    Args:
        doc: Drawing to search.
        uid: Logical entity uid stored in XDATA.

    Returns:
        ``(entity, ld_app_dict)``.

    Raises:
        AssertionError: If no entity exists for ``uid``.
    """
    ent = find_entity_by_uid(doc, uid)
    assert ent is not None, f"no entity for uid {uid!r}"
    return ent, read_ld_app_dict(ent)


def wire_polyline_points(doc: Drawing, wire_uid: str) -> list[tuple[float, float]]:
    """Vertex list of a wire polyline entity (LWPOLYLINE etc.) in document units.

    Args:
        doc: Drawing containing the wire.
        wire_uid: Wire entity uid.

    Returns:
        Ordered (x, y) vertices.

    Raises:
        AssertionError: If the entity is missing or has no ``points()`` iterator.
    """
    ent = find_entity_by_uid(doc, wire_uid)
    assert ent is not None
    out: list[tuple[float, float]] = []
    with ent.points() as p:
        for row in p:
            x, y, *_ = row
            out.append((float(x), float(y)))
    return out


def insert_world_xy(doc: Drawing, uid: str) -> tuple[float, float]:
    """INSERT insertion point in WCS for a symbol uid.

    Args:
        doc: Drawing to search.
        uid: INSERT entity uid.

    Returns:
        ``(x, y)`` insertion coordinates.

    Raises:
        AssertionError: If the entity is missing or not an INSERT.
    """
    ins = find_entity_by_uid(doc, uid)
    assert ins is not None and ins.dxftype() == "INSERT"
    return float(ins.dxf.insert.x), float(ins.dxf.insert.y)


def lwpolyline_first_vertex_xy(doc: Drawing, wire_uid: str) -> tuple[float, float]:
    """First vertex of a wire entity using ``get_points('xy')`` (test assertions).

    Args:
        doc: Drawing containing the wire.
        wire_uid: Wire entity uid.

    Returns:
        First (x, y) vertex.

    Raises:
        AssertionError: If the entity is missing or has no vertices.
    """
    ent = find_entity_by_uid(doc, wire_uid)
    assert ent is not None
    rows = list(ent.get_points("xy"))
    assert rows
    return (float(rows[0][0]), float(rows[0][1]))
