"""Regression tests for limited OSNAP behavior."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.tests.support.qt_offscreen import ensure_qapplication_offscreen
from logic_cad.ui.items.user_geometry_items import UserLineItem
from logic_cad.ui.scene import DiagramScene
from logic_cad.ui.scene_item.osnap import pick_osnap_candidate
from logic_cad.ui.snap_utils import scene_pos_from_dxf


@dataclass
class _FakePortSymbol:
    scene_point: QPointF

    def port_at_scene_pos(self, _scene_pos: QPointF) -> str | None:
        return None

    def port_keys(self) -> tuple[str, ...]:
        return ("IN0_LOGIC",)

    def port_scene_pos(self, _port_key: str) -> QPointF | None:
        return self.scene_point


def test_pick_osnap_candidate_wire_port_requires_explicit_enable() -> None:
    ensure_qapplication_offscreen()
    fake_port = _FakePortSymbol(QPointF(12.0, -7.0))
    disabled = pick_osnap_candidate(
        QPointF(12.2, -7.2),
        selected_items=[],
        symbol_items={"sym1": fake_port},
        include_user_line_endpoints=False,
        include_wire_ports=False,
    )
    enabled = pick_osnap_candidate(
        QPointF(12.2, -7.2),
        selected_items=[],
        symbol_items={"sym1": fake_port},
        include_user_line_endpoints=False,
        include_wire_ports=True,
    )
    assert disabled is None
    assert enabled is not None
    assert enabled.kind == "wire_port"
    assert enabled.symbol_uid == "sym1"
    assert enabled.port_key == "IN0_LOGIC"


def test_pick_osnap_candidate_user_line_endpoint_requires_selection() -> None:
    ensure_qapplication_offscreen()
    user_line = UserLineItem("sk1", 10.0, 5.0, 40.0, 5.0)
    scene_pos = scene_pos_from_dxf(10.5, 5.0)
    not_selected = pick_osnap_candidate(
        scene_pos,
        selected_items=[],
        symbol_items={},
        include_user_line_endpoints=True,
        include_wire_ports=False,
    )
    selected = pick_osnap_candidate(
        scene_pos,
        selected_items=[user_line],
        symbol_items={},
        include_user_line_endpoints=True,
        include_wire_ports=False,
    )
    assert not_selected is None
    assert selected is not None
    assert selected.kind == "user_line_endpoint"


def test_scene_line_end_osnap_falls_back_to_grid_when_no_candidate() -> None:
    ensure_qapplication_offscreen()
    scene = DiagramScene(LogicDiagram.new())
    p = scene._line_end_dxf((0.0, 0.0), scene_pos_from_dxf(2.2, 3.1), False)  # noqa: SLF001
    assert p == (2.0, 3.0)


def test_scene_wire_port_osnap_only_when_allowed() -> None:
    ensure_qapplication_offscreen()
    scene = DiagramScene(LogicDiagram.new())
    fake = _FakePortSymbol(QPointF(40.0, -20.0))
    scene._symbol_items = {"sym1": fake}  # type: ignore[assignment]  # noqa: SLF001
    blocked = scene._wire_port_hit_at_scene_pos(QPointF(40.8, -20.6), allow_osnap=False)  # noqa: SLF001
    allowed = scene._wire_port_hit_at_scene_pos(QPointF(40.8, -20.6), allow_osnap=True)  # noqa: SLF001
    assert blocked is None
    assert allowed is not None
    assert allowed[0] == "sym1"
    assert allowed[1] == "IN0_LOGIC"
