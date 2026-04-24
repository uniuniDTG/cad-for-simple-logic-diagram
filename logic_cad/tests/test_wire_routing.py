"""Manhattan routing."""

from logic_cad.core.routing import path_hits_obstacles, route_manhattan


def test_l_route():
    pts = route_manhattan((0, 0), (3, 2))
    assert pts[0] == (0, 0)
    assert pts[-1] == (3, 2)
    assert len(pts) == 3


def test_wraparound_candidate_routes_around_large_obstacle_without_ovg_fallback():
    obstacle = [(1.0, -80.0, 30.0, 80.0)]
    pts = route_manhattan(
        (0.0, 0.0),
        (4.0, 100.0),
        obstacle,
        src_facing=(1, 0),
        dst_facing=(1, 0),
    )
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (4.0, 100.0)
    assert not path_hits_obstacles(pts, obstacle)
