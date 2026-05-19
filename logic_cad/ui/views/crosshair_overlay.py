"""Viewport overlay for diagram crosshair (does not repaint the graphics scene)."""

from __future__ import annotations

from PySide6.QtCore import QLineF, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from logic_cad.ui.app_user_settings import CrosshairMode

_CROSSHAIR_PEN_PAD_PX = 3


def crosshair_paint_bounds(
    mode: CrosshairMode,
    cx: int,
    cy: int,
    vr: QRect,
    local_half_px: int,
    center_box_side_px: int,
    pen_pad: int = _CROSSHAIR_PEN_PAD_PX,
) -> QRect:
    """Return a viewport rectangle covering the crosshair and center box for one cursor position."""
    if mode == CrosshairMode.NONE:
        return QRect()
    box_r = QRect()
    if center_box_side_px > 0:
        left = cx - center_box_side_px // 2
        top = cy - center_box_side_px // 2
        box_r = QRect(
            left - pen_pad,
            top - pen_pad,
            center_box_side_px + 2 * pen_pad,
            center_box_side_px + 2 * pen_pad,
        )
    if mode == CrosshairMode.FULL:
        h_strip = QRect(vr.left(), cy - pen_pad, vr.width(), 2 * pen_pad + 1)
        v_strip = QRect(cx - pen_pad, vr.top(), 2 * pen_pad + 1, vr.height())
        return h_strip.united(v_strip).united(box_r).intersected(vr)
    h = max(1, local_half_px)
    arm_h = QRect(cx - h - pen_pad, cy - pen_pad, 2 * (h + pen_pad) + 1, 2 * pen_pad + 1)
    arm_v = QRect(cx - pen_pad, cy - h - pen_pad, 2 * pen_pad + 1, 2 * (h + pen_pad) + 1)
    return arm_h.united(arm_v).united(box_r).intersected(vr)


def _paint_crosshair_full_viewport(
    painter: QPainter,
    ix: int,
    iy: int,
    vr: QRect,
    side: int,
) -> None:
    """Draw full-span crosshair in viewport pixel coordinates."""
    if side <= 0:
        painter.drawLine(QLineF(vr.left(), iy, vr.right(), iy))
        painter.drawLine(QLineF(ix, vr.top(), ix, vr.bottom()))
        return
    left = ix - side // 2
    top = iy - side // 2
    right_excl = left + side
    bottom_excl = top + side
    if left - 1 >= vr.left():
        painter.drawLine(QLineF(vr.left(), iy, left - 1, iy))
    if right_excl <= vr.right():
        painter.drawLine(QLineF(right_excl, iy, vr.right(), iy))
    if top - 1 >= vr.top():
        painter.drawLine(QLineF(ix, vr.top(), ix, top - 1))
    if bottom_excl <= vr.bottom():
        painter.drawLine(QLineF(ix, bottom_excl, ix, vr.bottom()))


def _paint_crosshair_local_viewport(
    painter: QPainter,
    ix: int,
    iy: int,
    h: int,
    side: int,
) -> None:
    """Draw short crosshair arms in viewport pixel coordinates."""
    if side <= 0:
        painter.drawLine(QLineF(ix - h, iy, ix + h, iy))
        painter.drawLine(QLineF(ix, iy - h, ix, iy + h))
        return
    left = ix - side // 2
    top = iy - side // 2
    right_excl = left + side
    bottom_excl = top + side
    x_lo, x_hi = ix - h, ix + h
    x2 = min(x_hi, left - 1)
    if x_lo <= x2:
        painter.drawLine(QLineF(x_lo, iy, x2, iy))
    x1 = max(x_lo, right_excl)
    if x1 <= x_hi:
        painter.drawLine(QLineF(x1, iy, x_hi, iy))
    y_lo, y_hi = iy - h, iy + h
    y2 = min(y_hi, top - 1)
    if y_lo <= y2:
        painter.drawLine(QLineF(ix, y_lo, ix, y2))
    y1 = max(y_lo, bottom_excl)
    if y1 <= y_hi:
        painter.drawLine(QLineF(ix, y1, ix, y_hi))


def _paint_crosshair_center_box_viewport(
    painter: QPainter,
    ix: int,
    iy: int,
    side: int,
) -> None:
    """Draw the hollow square at the crosshair center in viewport pixels."""
    if side <= 0:
        return
    painter.setBrush(Qt.BrushStyle.NoBrush)
    left = ix - side // 2
    top = iy - side // 2
    painter.drawRect(left, top, side, side)


class CrosshairOverlay(QWidget):
    """Child of the diagram viewport; paints crosshair without invalidating the scene."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        # Child of QGraphicsView (not its viewport): WA_TranslucentBackground composites over the scene.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self._mode: CrosshairMode = CrosshairMode.NONE
        self._local_half_px: int = 20
        self._center_box_side_px: int = 0
        self._cursor_pos: QPoint | None = None
        self._pan_active: bool = False

    def set_crosshair_style(
        self,
        mode: CrosshairMode,
        local_half_px: int,
        center_box_side_px: int,
    ) -> None:
        """Apply crosshair display parameters and repaint when they change."""
        prev_pos = self._cursor_pos
        dirty_before = self._damage_for_position(prev_pos) if prev_pos is not None else QRect()
        self._mode = mode
        self._local_half_px = local_half_px
        self._center_box_side_px = center_box_side_px
        if mode == CrosshairMode.NONE:
            self._cursor_pos = None
            self.hide()
            if dirty_before.isValid() and not dirty_before.isEmpty():
                self.update(dirty_before)
            return
        self.show()
        self.raise_()
        if prev_pos is not None:
            self._repaint_union(prev_pos, prev_pos)
        else:
            self.update()

    def set_pan_active(self, active: bool) -> None:
        """Hide crosshair ink while middle-button pan is active."""
        if self._pan_active == active:
            return
        self._pan_active = active
        if self._cursor_pos is not None:
            self._repaint_at(self._cursor_pos)

    def sync_cursor_viewport_pos(self, pos: QPoint | None) -> None:
        """Move crosshair to *pos* (viewport coordinates) with minimal dirty region."""
        if self._mode == CrosshairMode.NONE:
            self._cursor_pos = pos
            return
        if self._pan_active:
            self._cursor_pos = pos
            return
        prev = self._cursor_pos
        self._cursor_pos = pos
        if pos is None:
            if prev is not None:
                dirty = self._damage_for_position(prev)
                if dirty.isValid() and not dirty.isEmpty():
                    self.update(dirty)
            return
        if prev is None:
            self._repaint_at(pos)
            return
        dirty = self._damage_union(prev, pos)
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()

    def _damage_for_position(self, pos: QPoint) -> QRect:
        return crosshair_paint_bounds(
            self._mode,
            int(pos.x()),
            int(pos.y()),
            self.rect(),
            self._local_half_px,
            self._center_box_side_px,
            pen_pad=_CROSSHAIR_PEN_PAD_PX,
        )

    def _damage_union(self, prev: QPoint, cur: QPoint) -> QRect:
        d0 = self._damage_for_position(prev)
        d1 = self._damage_for_position(cur)
        if not d0.isValid() or d0.isEmpty():
            return d1
        if not d1.isValid() or d1.isEmpty():
            return d0
        return d0.united(d1).intersected(self.rect())

    def _repaint_at(self, pos: QPoint) -> None:
        dirty = self._damage_for_position(pos)
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()

    def _repaint_union(self, prev: QPoint, cur: QPoint) -> None:
        dirty = self._damage_union(prev, cur)
        if dirty.isValid() and not dirty.isEmpty():
            self.update(dirty)
        else:
            self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._mode != CrosshairMode.NONE and self._cursor_pos is not None:
            self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._mode == CrosshairMode.NONE or self._pan_active or self._cursor_pos is None:
            return
        ix = int(self._cursor_pos.x())
        iy = int(self._cursor_pos.y())
        vr = self.rect()
        side = self._center_box_side_px
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            pen = QPen(QColor(180, 180, 190, 210))
            pen.setWidth(1)
            pen.setCosmetic(True)
            painter.setPen(pen)
            if self._mode == CrosshairMode.FULL:
                _paint_crosshair_full_viewport(painter, ix, iy, vr, side)
            elif self._mode == CrosshairMode.LOCAL:
                h = max(1, self._local_half_px)
                _paint_crosshair_local_viewport(painter, ix, iy, h, side)
            _paint_crosshair_center_box_viewport(painter, ix, iy, side)
        finally:
            painter.end()
