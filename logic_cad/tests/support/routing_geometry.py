"""Shared routing test geometry: obstacle constants and grid-snapped endpoint pairs."""

from logic_cad.core.model.constants import GRID_PITCH
from logic_cad.core.routing.polyline import snap_to_grid

# Large axis-aligned rectangle that blocks typical detours around short horizontal spans
# (used in four-layer relaxed vs full-hard tests).
ROUTING_TEST_BLOCKING_WALL_MM = (-40.0, -40.0, 40.0, 40.0)


def snapped_segment_default_diagonal(
    pitch: float = GRID_PITCH,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Return grid-snapped endpoints used across OVG / profile smoke tests.

    The pair origin to (80 mm, 40 mm) yields a non-trivial Manhattan path on the
    default grid and matches repeated patterns in ``test_routing_env_overrides``,
    ``test_routing_hybrid_fixed_ovg``, and ``test_fixed_manhattan_facing_detours``.

    Args:
        pitch: Grid pitch (defaults to :data:`GRID_PITCH`).

    Returns:
        ``(p0, p1)`` with both points passed through :func:`snap_to_grid`.
    """
    p0 = snap_to_grid(0.0, 0.0, pitch)
    p1 = snap_to_grid(80.0, 40.0, pitch)
    return p0, p1
