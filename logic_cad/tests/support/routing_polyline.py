"""Manhattan polyline metrics for routing tests."""

from logic_cad.core.routing import polyline_segments


def manhattan_polyline_length(pts: list[tuple[float, float]]) -> float:
    """Sum of L1 segment lengths along a polyline.

    Args:
        pts: Vertex list in document units.

    Returns:
        Total Manhattan length.
    """
    total = 0.0
    for a0, a1 in polyline_segments(pts):
        total += abs(a1[0] - a0[0]) + abs(a1[1] - a0[1])
    return total


def manhattan_polyline_has_collinear_foldback(pts: list[tuple[float, float]]) -> bool:
    """True if three consecutive collinear vertices have a middle vertex off the segment.

    Args:
        pts: Polyline vertices.

    Returns:
        Whether a fold-back (backtrack) appears on an axis-aligned three-vertex run.
    """
    for i in range(len(pts) - 2):
        a, b, c = pts[i], pts[i + 1], pts[i + 2]
        if abs(a[1] - b[1]) < 1e-9 and abs(b[1] - c[1]) < 1e-9:
            if not (min(a[0], c[0]) <= b[0] <= max(a[0], c[0])):
                return True
        if abs(a[0] - b[0]) < 1e-9 and abs(b[0] - c[0]) < 1e-9:
            if not (min(a[1], c[1]) <= b[1] <= max(a[1], c[1])):
                return True
    return False
