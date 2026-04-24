"""Graphics item for WIRE_ARROW open LWPOLYLINE (IN-side arrow head)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QStyle, QStyleOptionGraphicsItem, QWidget

from logic_cad.core.model.constants import LINETYPE_LOGIC
from logic_cad.ui.scene_item.z_order import CANVAS_Z_SYMBOL_AND_WIRE_ARROW
from logic_cad.ui.items.wire_item import apply_dxf_linetype_to_pen, dxf_to_scene


class WireArrowItem(QGraphicsPathItem):
    """Scene item for a ``WIRE_ARROW`` open polyline (two wings meeting at IN).

    Coordinates follow DXF mm with Y flipped for Qt via ``dxf_to_scene``, matching
    :class:`~logic_cad.ui.items.wire_item.WireItem`.
    """

    def __init__(
        self,
        points_xy: list[tuple[float, float]],
        *,
        linetype: str = LINETYPE_LOGIC,
        stroke_color: QColor | None = None,
        parent=None,
    ) -> None:
        """Build a path through *points_xy* and apply DXF-like linetype styling.

        Args:
            points_xy: Polyline vertices in DXF mm (at least two for a visible path).
            linetype: DXF linetype name (e.g. CONTINUOUS / DASHED).
            stroke_color: BYLAYER-resolved stroke; default gray when omitted.
            parent: Optional ``QGraphicsItem`` parent.
        """
        super().__init__(parent)
        self._points_xy = list(points_xy)
        self._linetype = str(linetype or LINETYPE_LOGIC)
        path = QPainterPath()
        if len(self._points_xy) >= 2:
            path.moveTo(dxf_to_scene(*self._points_xy[0]))
            for xy in self._points_xy[1:]:
                path.lineTo(dxf_to_scene(*xy))
        self.setPath(path)
        base = QColor(200, 200, 210) if stroke_color is None else QColor(stroke_color)
        pen = QPen(base, 0)
        pen.setCosmetic(True)
        apply_dxf_linetype_to_pen(pen, self._linetype)
        self.setPen(pen)
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        # Above wire centerlines; clicks pass through to WireItem (lower Z).
        # Same band as SymbolItem; selection highlight follows parent WIRE only.
        self.setZValue(CANVAS_Z_SYMBOL_AND_WIRE_ARROW)

    def paint(self, painter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        """Delegates to the base path paint (non-selectable; no separate selection style)."""
        super().paint(painter, option, widget)
