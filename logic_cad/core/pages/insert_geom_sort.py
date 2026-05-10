"""Shared INSERT insert-point keys for deterministic ordering across page features."""

from __future__ import annotations


def insert_geom_sort_tuple(entity) -> tuple[float, float, str]:
    """Build a lexicographic sort key from INSERT placement (stable tie-break).

    Ordering matches historical PAGE_REF behavior: sort top-to-bottom in model Y
    (negate ``insert.y``), then left-to-right by ``insert.x``, then DXF handle.

    Args:
        entity: An ``INSERT`` (or any entity with ``dxf.insert`` and ``dxf.handle``).

    Returns:
        Tuple ``(-y, x, handle)`` for use as a sort-key suffix.
    """

    return (-float(entity.dxf.insert.y), float(entity.dxf.insert.x), str(entity.dxf.handle))
