"""Axis-aligned obstacle rectangles vs Manhattan segments (inflated open-interior test)."""

from __future__ import annotations

from logic_cad.core.model.constants import ROUTING_PATH_OBSTACLE_INFLATE_MM


def segment_intersects_rect_open(
    a0: tuple[float, float],
    a1: tuple[float, float],
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    eps: float = 1e-6,
) -> bool:
    """Axis-aligned segment vs open rectangle interior (Manhattan paths)."""
    x1, y1 = a0
    x2, y2 = a1
    xa, xb = min(x1, x2), max(x1, x2)
    ya, yb = min(y1, y2), max(y1, y2)
    if xb < xmin + eps or xa > xmax - eps or yb < ymin + eps or ya > ymax - eps:
        return False
    if abs(y2 - y1) < eps:
        y = y1
        if not (ymin + eps < y < ymax - eps):
            return False
        return max(xa, xmin) < min(xb, xmax) - eps
    if abs(x2 - x1) < eps:
        x = x1
        if not (xmin + eps < x < xmax - eps):
            return False
        return max(ya, ymin) < min(yb, ymax) - eps
    return False


def _inflate_rect(
    xmin: float, ymin: float, xmax: float, ymax: float, m: float
) -> tuple[float, float, float, float]:
    return (xmin - m, ymin - m, xmax + m, ymax + m)


def obstacle_rects_inflated(
    obstacles: list[tuple[float, float, float, float]],
    inflate_mm: float = ROUTING_PATH_OBSTACLE_INFLATE_MM,
) -> list[tuple[float, float, float, float]]:
    return [_inflate_rect(x0, y0, x1, y1, inflate_mm) for x0, y0, x1, y1 in obstacles]


def segment_hits_obstacle_rects(
    a0: tuple[float, float],
    a1: tuple[float, float],
    inflated_rects: list[tuple[float, float, float, float]],
) -> bool:
    for xmin, ymin, xmax, ymax in inflated_rects:
        if segment_intersects_rect_open(a0, a1, xmin, ymin, xmax, ymax):
            return True
    return False


def path_hits_obstacles(
    pts: list[tuple[float, float]],
    obstacles: list[tuple[float, float, float, float]],
    inflate_mm: float = ROUTING_PATH_OBSTACLE_INFLATE_MM,
) -> bool:
    if len(pts) < 2:
        return False
    inflated = obstacle_rects_inflated(obstacles, inflate_mm)
    return path_hits_obstacle_rects(pts, inflated)


def path_hits_obstacle_rects(
    pts: list[tuple[float, float]],
    inflated_rects: list[tuple[float, float, float, float]],
) -> bool:
    if len(pts) < 2:
        return False
    for i in range(len(pts) - 1):
        if segment_hits_obstacle_rects(pts[i], pts[i + 1], inflated_rects):
            return True
    return False
