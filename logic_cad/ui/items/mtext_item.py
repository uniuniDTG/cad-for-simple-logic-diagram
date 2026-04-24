"""MTEXT from paper space block → path-based QGraphicsItem (DXF y-up → scene y-down)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from logic_cad.core.text.layout_resolver import NormalizedTextLayout
from logic_cad.ui.block_paint import mtext_path_bounds_item_local, paint_mtext_path_mm


class DxfMTextItem(QGraphicsItem):
    """Path-based multiline text item with DXF mm semantics."""

    def __init__(self, layout: NormalizedTextLayout) -> None:
        """Create MTEXT graphics item from normalized layout.

        Args:
            layout: Shared text layout semantics resolved from a DXF MTEXT entity.
        """
        super().__init__()
        self._layout = layout
        self._color = QColor(210, 212, 218)
        self._line_gap_ratio = 0.2
        br = mtext_path_bounds_item_local(
            layout.text,
            layout.height_mm,
            width_mm=layout.width_mm,
            line_gap_ratio=self._line_gap_ratio,
            halign=layout.halign,
            valign=layout.valign,
            width_fac=layout.width_factor,
            font_family=layout.font_family,
            font_families=layout.font_families,
        )
        self._bounds = br if br is not None and not br.isEmpty() else QRectF(-0.5, -0.5, 1.0, 1.0)
        self.setPos(QPointF(layout.anchor_x, -layout.anchor_y))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setTransformOriginPoint(0.0, 0.0)
        self.setRotation(-float(layout.rotation_deg))

    def setDefaultTextColor(self, color: QColor) -> None:
        """Keep compatibility with prior ``QGraphicsTextItem`` API."""

        self._color = QColor(color)
        self.update()

    def boundingRect(self) -> QRectF:
        """Return cached item-local text bounds."""

        return self._bounds

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw MTEXT using mm-based multiline path rendering."""

        _ = option
        _ = widget
        paint_mtext_path_mm(
            painter,
            self._layout.text,
            self._layout.height_mm,
            QPointF(0.0, 0.0),
            width_mm=self._layout.width_mm,
            line_gap_ratio=self._line_gap_ratio,
            halign=self._layout.halign,
            valign=self._layout.valign,
            width_fac=self._layout.width_factor,
            fill=self._color,
            font_family=self._layout.font_family,
            font_families=self._layout.font_families,
        )
