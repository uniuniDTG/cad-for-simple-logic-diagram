"""Port facing hints: route relation classification and wraparound L-shaped detours."""

from __future__ import annotations

from .polyline import snap_to_grid


def axis_facing(facing: tuple[int, int] | None) -> tuple[int, int] | None:
    if facing is None:
        return None
    fx, fy = facing
    if abs(fx) >= abs(fy):
        if abs(fx) < 1e-9:
            return None
        return (1 if fx > 0 else -1, 0)
    if abs(fy) < 1e-9:
        return None
    return (0, 1 if fy > 0 else -1)


def _dot_dir(a: tuple[int, int], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def classify_route_relation(
    src: tuple[float, float],
    dst: tuple[float, float],
    src_facing: tuple[int, int] | None,
    dst_facing: tuple[int, int] | None,
) -> str:
    src_dir = axis_facing(src_facing)
    dst_dir = axis_facing(dst_facing)
    if src_dir is None:
        return "unknown"
    to_dst = (dst[0] - src[0], dst[1] - src[1])
    src_dot = _dot_dir(src_dir, to_dst)
    if src_dot < 0:
        return "backward"
    if dst_dir is not None and src_dir == dst_dir:
        return "parallel_same"
    if abs(src_dot) < 1e-9:
        return "sideways"
    return "forward"


def compute_bypass_lines(
    src: tuple[float, float],
    dst: tuple[float, float],
    obstacles: list[tuple[float, float, float, float]],
    pitch: float,
    margin_grids: int = 2,
) -> dict[str, float]:
    margin = margin_grids * pitch
    if obstacles:
        y_above = min(b[1] for b in obstacles) - margin
        y_below = max(b[3] for b in obstacles) + margin
        x_left = min(b[0] for b in obstacles) - margin
        x_right = max(b[2] for b in obstacles) + margin
    else:
        y_above = min(src[1], dst[1]) - margin
        y_below = max(src[1], dst[1]) + margin
        x_left = min(src[0], dst[0]) - margin
        x_right = max(src[0], dst[0]) + margin
    return {
        "y_above": snap_to_grid(0.0, y_above, pitch)[1],
        "y_below": snap_to_grid(0.0, y_below, pitch)[1],
        "x_left": snap_to_grid(x_left, 0.0, pitch)[0],
        "x_right": snap_to_grid(x_right, 0.0, pitch)[0],
    }


def gen_wraparound_candidates(
    src: tuple[float, float],
    dst: tuple[float, float],
    src_facing: tuple[int, int] | None,
    dst_facing: tuple[int, int] | None,
    bypass: dict[str, float],
) -> list[list[tuple[float, float]]]:
    x0, y0 = src
    x1, y1 = dst
    relation = classify_route_relation(src, dst, src_facing, dst_facing)
    if relation not in {"backward", "parallel_same"}:
        return []
    candidates = [
        [(x0, y0), (x0, bypass["y_above"]), (x1, bypass["y_above"]), (x1, y1)],
        [(x0, y0), (x0, bypass["y_below"]), (x1, bypass["y_below"]), (x1, y1)],
        [(x0, y0), (bypass["x_left"], y0), (bypass["x_left"], y1), (x1, y1)],
        [(x0, y0), (bypass["x_right"], y0), (bypass["x_right"], y1), (x1, y1)],
    ]
    src_dir = axis_facing(src_facing)
    dst_dir = axis_facing(dst_facing)
    if src_dir is not None and dst_dir is not None and src_dir == dst_dir:
        if src_dir[0] != 0:
            preferred_x = bypass["x_right"] if src_dir[0] > 0 else bypass["x_left"]
            candidates.insert(0, [(x0, y0), (preferred_x, y0), (preferred_x, y1), (x1, y1)])
        else:
            preferred_y = bypass["y_below"] if src_dir[1] > 0 else bypass["y_above"]
            candidates.insert(0, [(x0, y0), (x0, preferred_y), (x1, preferred_y), (x1, y1)])
    return candidates
