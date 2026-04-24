"""Hub cardinal occupancy for WIRE_BRANCH / CHECKPOINT OUT0_MULTI."""

from logic_cad.core.routing.occupancy import banned_out_cardinals_for_hub, hub_ray_in_from_polyline


def test_banned_out_collects_in_ray_and_existing_out_rays():
    layout = "Model"
    wire_rows = [
        ("w1", {"dst": "hub", "dst_port": "IN0_MULTI"}, [(-5.0, 0.0), (0.0, 0.0)]),
        ("w2", {"src": "hub", "src_port": "OUT0_MULTI"}, [(0.0, 0.0), (0.0, 5.0)]),
    ]
    pts_queue = [r[2] for r in wire_rows]

    def iter_wire_meta(name):
        assert name == layout
        for wu, d, _ in wire_rows:
            yield None, wu, d

    def polyline_points_fn(_e):
        return pts_queue.pop(0)

    banned = banned_out_cardinals_for_hub(
        layout,
        "hub",
        iter_wire_meta=iter_wire_meta,
        polyline_points_fn=polyline_points_fn,
    )
    assert (-1, 0) in banned  # IN from west
    assert (0, 1) in banned  # OUT to north


def test_exclude_wire_uids_omits_that_wire_ray():
    layout = "Model"

    def iter_wire_meta(name):
        yield None, "skip_me", {"src": "hub", "src_port": "OUT0_MULTI"}

    def polyline_points_fn(_e):
        return [(0.0, 0.0), (3.0, 0.0)]

    banned = banned_out_cardinals_for_hub(
        layout,
        "hub",
        iter_wire_meta=iter_wire_meta,
        polyline_points_fn=polyline_points_fn,
        exclude_wire_uids={"skip_me"},
    )
    assert banned == set()


def test_hub_ray_in_from_polyline():
    # Last vertex is the hub IN port; previous is along the incoming segment.
    assert hub_ray_in_from_polyline([(-2.0, 0.0), (0.0, 0.0)]) == (-1, 0)
