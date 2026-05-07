"""Wire segment and hub cardinal-ray occupancy for constraint-first routing."""

from __future__ import annotations

from logic_cad.core.routing.polyline import snap_to_grid

# Cardinal step on grid: (dx, dy) in {-1,0,1}^2 \ {(0,0)}
Cardinal = tuple[int, int]

CARDINALS: tuple[Cardinal, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


def cardinal_from_delta(dx: float, dy: float, eps: float = 1e-9) -> Cardinal | None:
    """Map a Manhattan delta to a unit cardinal; None if degenerate."""
    if abs(dx) < eps and abs(dy) < eps:
        return None
    if abs(dx) >= abs(dy):
        return (1 if dx > 0 else -1, 0)
    return (0, 1 if dy > 0 else -1)


def _norm_segment_key(
    a: tuple[float, float],
    b: tuple[float, float],
    pitch: float,
    eps: float = 1e-9,
) -> tuple[str, float, float, float] | None:
    """Axis-aligned segment key for overlap lookup (world snapped coords)."""
    x0, y0 = snap_to_grid(a[0], a[1], pitch)
    x1, y1 = snap_to_grid(b[0], b[1], pitch)
    if abs(x0 - x1) < eps and abs(y0 - y1) < eps:
        return None
    if abs(x0 - x1) < eps:
        return ("v", x0, min(y0, y1), max(y0, y1))
    if abs(y0 - y1) < eps:
        return ("h", y0, min(x0, x1), max(x0, x1))
    return None


def segment_keys_for_path(
    pts: list[tuple[float, float]],
    pitch: float,
) -> set[tuple[str, float, float, float]]:
    """All normalized segment keys for a Manhattan polyline."""
    out: set[tuple[str, float, float, float]] = set()
    for i in range(len(pts) - 1):
        k = _norm_segment_key(pts[i], pts[i + 1], pitch)
        if k is not None:
            out.add(k)
    return out


def hub_ray_out_from_polyline(pts: list[tuple[float, float]]) -> Cardinal | None:
    """Cardinal direction along first edge from port (src) outward."""
    if len(pts) < 2:
        return None
    return cardinal_from_delta(pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])


def hub_ray_in_from_polyline(pts: list[tuple[float, float]]) -> Cardinal | None:
    """Cardinal direction from IN port along wire toward interior (second vertex from end)."""
    if len(pts) < 2:
        return None
    return cardinal_from_delta(pts[-2][0] - pts[-1][0], pts[-2][1] - pts[-1][1])


def banned_out_cardinals_for_hub(
    layout_name: str,
    hub_uid: str,
    *,
    iter_wire_meta,
    polyline_points_fn,
    exclude_wire_uids: set[str] | None = None,
) -> set[Cardinal]:
    """Occupied rays at WIRE_BRANCH/CHECKPOINT for a new hub-origin wire."""
    ex = exclude_wire_uids or set()
    banned: set[Cardinal] = set()
    for _e, wu, d in iter_wire_meta(layout_name):
        if not wu or wu in ex:
            continue
        if d.get("dst") == hub_uid and str(d.get("dst_port") or "") == "IN0_MULTI":
            pts = polyline_points_fn(_e)
            r = hub_ray_in_from_polyline(pts)
            if r is not None:
                banned.add(r)
        if d.get("dst") == hub_uid and str(d.get("dst_port") or "") == "INOUT0_MULTI":
            pts = polyline_points_fn(_e)
            r = hub_ray_in_from_polyline(pts)
            if r is not None:
                banned.add(r)
        if d.get("src") == hub_uid and str(d.get("src_port") or "") == "OUT0_MULTI":
            pts = polyline_points_fn(_e)
            r = hub_ray_out_from_polyline(pts)
            if r is not None:
                banned.add(r)
        if d.get("src") == hub_uid and str(d.get("src_port") or "") == "INOUT0_MULTI":
            pts = polyline_points_fn(_e)
            r = hub_ray_out_from_polyline(pts)
            if r is not None:
                banned.add(r)
    return banned
