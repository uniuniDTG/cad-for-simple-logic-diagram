"""CAD-style toolbar icons for sketch and wire tools (QPainter, no external files)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF


def _pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    return pm


def _pen(r: int = 220, g: int = 224, b: int = 232, width: float = 1.8) -> QPen:
    pen = QPen(QColor(r, g, b))
    pen.setWidthF(width)
    pen.setCapStyle(Qt.PenCapStyle.FlatCap)
    pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
    return pen


def _endpoint_square(p: QPainter, x: float, y: float, half: float = 2.0) -> None:
    """Draw a small filled square at (x, y) as a CAD vertex/endpoint marker."""
    p.fillRect(int(x - half), int(y - half), int(half * 2), int(half * 2), QColor(100, 180, 220))


def sketch_line_icon(*, size: int = 26) -> QIcon:
    """Diagonal line with endpoint squares — CAD line tool."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen())
    m = max(4, size // 6)
    x1, y1 = float(m), float(size - m)
    x2, y2 = float(size - m), float(m)
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))
    _endpoint_square(p, x1, y1)
    _endpoint_square(p, x2, y2)
    p.end()
    return QIcon(pm)


def sketch_circle_icon(*, size: int = 26) -> QIcon:
    """Circle with center crosshair — CAD circle tool."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen())
    m = max(4, size // 6)
    p.drawEllipse(m, m, size - 2 * m, size - 2 * m)
    cx, cy = size / 2.0, size / 2.0
    cross = max(3, size // 8)
    dim_pen = _pen(100, 180, 220, 1.0)
    p.setPen(dim_pen)
    p.drawLine(QPointF(cx - cross, cy), QPointF(cx + cross, cy))
    p.drawLine(QPointF(cx, cy - cross), QPointF(cx, cy + cross))
    p.end()
    return QIcon(pm)


def sketch_text_icon(*, size: int = 26) -> QIcon:
    """'T' glyph with baseline — CAD text placement tool."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen())
    top = max(4, size // 5)
    bot = size - max(4, size // 6)
    cx = size / 2.0
    hw = max(5, size // 3)
    p.drawLine(QPointF(cx - hw, top), QPointF(cx + hw, top))
    p.drawLine(QPointF(cx, top), QPointF(cx, bot))
    base_pen = _pen(100, 180, 220, 1.0)
    p.setPen(base_pen)
    p.drawLine(QPointF(cx - hw - 1, bot + 2), QPointF(cx + hw + 1, bot + 2))
    p.end()
    return QIcon(pm)


def sketch_cloud_icon(*, size: int = 26) -> QIcon:
    """Revision cloud style arc chain."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen(190, 220, 255, 1.6))
    m = max(3, size // 7)
    top = float(m)
    left = float(m)
    right = float(size - m)
    bottom = float(size - m)
    step = max(4, size // 5)
    x = left
    while x < right - 0.1:
        nx = min(right, x + step)
        p.drawArc(int(x), int(top), int(nx - x), int(step), 0, 180 * 16)
        x = nx
    y = top
    while y < bottom - 0.1:
        ny = min(bottom, y + step)
        p.drawArc(int(right - step), int(y), int(step), int(ny - y), 270 * 16, 180 * 16)
        y = ny
    x = right
    while x > left + 0.1:
        nx = max(left, x - step)
        p.drawArc(int(nx), int(bottom - step), int(x - nx), int(step), 180 * 16, 180 * 16)
        x = nx
    y = bottom
    while y > top + 0.1:
        ny = max(top, y - step)
        p.drawArc(int(left), int(ny), int(step), int(y - ny), 90 * 16, 180 * 16)
        y = ny
    p.end()
    return QIcon(pm)


def wire_auto_icon(*, size: int = 26) -> QIcon:
    """L-shaped elbow connector with arrowhead — auto-routing wire tool."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen(220, 180, 100, 1.8))
    m = max(3, size // 7)
    mid_y = size // 2
    x1, y1 = float(m), float(size - m)
    xc, yc = float(m), float(mid_y)
    x2, y2 = float(size - m), float(mid_y)
    p.drawLine(QPointF(x1, y1), QPointF(xc, yc))
    p.drawLine(QPointF(xc, yc), QPointF(x2, y2))
    aw = max(3, size // 8)
    arrow = QPolygonF([
        QPointF(x2, y2),
        QPointF(x2 - aw, y2 - aw // 2),
        QPointF(x2 - aw, y2 + aw // 2),
    ])
    p.setBrush(QColor(220, 180, 100))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(arrow)
    _endpoint_square(p, x1, y1, 1.8)
    p.end()
    return QIcon(pm)


def wire_manual_icon(*, size: int = 26) -> QIcon:
    """Two-segment polyline with diamond midpoint — manual wire tool."""
    pm = _pixmap(size)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(_pen(180, 220, 140, 1.8))
    m = max(3, size // 7)
    x1, y1 = float(m), float(size - m)
    xm, ym = float(size // 2), float(size // 2)
    x2, y2 = float(size - m), float(m)
    p.drawLine(QPointF(x1, y1), QPointF(xm, ym))
    p.drawLine(QPointF(xm, ym), QPointF(x2, y2))
    dh = max(3, size // 9)
    diamond = QPolygonF([
        QPointF(xm, ym - dh),
        QPointF(xm + dh, ym),
        QPointF(xm, ym + dh),
        QPointF(xm - dh, ym),
    ])
    p.setBrush(QColor(180, 220, 140))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawPolygon(diamond)
    _endpoint_square(p, x1, y1, 1.8)
    _endpoint_square(p, x2, y2, 1.8)
    p.end()
    return QIcon(pm)
