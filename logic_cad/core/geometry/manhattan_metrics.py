"""Pure numeric helpers for Manhattan (taxicab / L1) distances in 2D.

Shared by routing, model indexing, and polyline utilities so ``abs(dx)+abs(dy)``
logic stays consistent and single-sourced.
"""

from __future__ import annotations


def manhattan_distance(
    a: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Return the L1 distance between two XY points.

    Args:
        a: First point ``(x, y)`` in consistent units (e.g. drawing mm).
        b: Second point in the same coordinate system as *a*.

    Returns:
        Sum of absolute axis deltas ``|a.x - b.x| + |a.y - b.y|``.
    """
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def manhattan_distance_via(
    a: tuple[float, float],
    via: tuple[float, float],
    b: tuple[float, float],
) -> float:
    """Return Manhattan length of the two-leg path *a* → *via* → *b*.

    Args:
        a: Path start in XY.
        via: Intermediate corner (not required to lie on a shortest global path *a*→*b*).
        b: Path end in XY.

    Returns:
        ``manhattan_distance(a, via) + manhattan_distance(via, b)``.
    """
    return manhattan_distance(a, via) + manhattan_distance(via, b)


def points_close_xy(
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    """Return True if both coordinates match within *eps*.

    Args:
        a: First XY point.
        b: Second XY point.
        eps: Absolute tolerance per axis.

    Returns:
        True when ``|a.x - b.x| < eps`` and ``|a.y - b.y| < eps``.
    """
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


def segment_is_horizontal(
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    """Return True if *a* and *b* share the same Y within *eps* (horizontal segment).

    Args:
        a: Segment start.
        b: Segment end.
        eps: Absolute tolerance on Y.

    Returns:
        True when the segment lies on a horizontal line (before considering length).
    """
    return abs(a[1] - b[1]) < eps


def segment_is_vertical(
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    """Return True if *a* and *b* share the same X within *eps* (vertical segment).

    Args:
        a: Segment start.
        b: Segment end.
        eps: Absolute tolerance on X.

    Returns:
        True when the segment lies on a vertical line (before considering length).
    """
    return abs(a[0] - b[0]) < eps


def segment_is_axis_aligned(
    a: tuple[float, float],
    b: tuple[float, float],
    eps: float = 1e-9,
) -> bool:
    """Return True if *a*→*b* is horizontal, vertical, or degenerate within *eps*.

    Args:
        a: Segment start.
        b: Segment end.
        eps: Absolute tolerance per axis.

    Returns:
        True when at least one axis delta is below *eps* (Manhattan-eligible segment).
    """
    return abs(a[0] - b[0]) < eps or abs(a[1] - b[1]) < eps


def truncated_grid_steps_sum(
    a: tuple[float, float],
    b: tuple[float, float],
    pitch: float,
) -> int:
    """Per-axis truncated grid steps: ``int(|Δx|/pitch) + int(|Δy|/pitch)``.

    Used for fixed-Manhattan detour bounds; this is **not** ``int(manhattan_distance(a, b) / pitch)``
    because flooring each axis before summing can yield a smaller value.

    Args:
        a: Start point in world units (e.g. mm).
        b: End point in the same units.
        pitch: Grid pitch; must be positive.

    Returns:
        Sum of per-axis truncated step counts.

    Raises:
        ValueError: If *pitch* is not positive.
    """
    if pitch <= 0:
        raise ValueError("pitch must be positive")
    return int(abs(a[0] - b[0]) / pitch) + int(abs(a[1] - b[1]) / pitch)
