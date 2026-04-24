"""Non-interactive Qt graphics for layout-space DXF entities without LD_APP ``uid``.

External CAD edits often drop XDATA; these helpers mirror PDF-visible geometry on the
canvas without participating in selection or Logic CAD editing workflows.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QStyleOptionGraphicsItem,
    QWidget,
)
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity
from ezdxf.math import ConstructionArc

from logic_cad.core.model.constants import (
    ENTITY_TYPE_WIRE_ARROW,
    LAYER_FRAME,
    LAYER_VPORT,
    LINETYPE_CONTINUOUS,
)
from logic_cad.core.model.layout_entity_layer_policy import is_hidden_for_passive_layout_primitive
from logic_cad.core.model.wire_layers import is_wire_layer
from logic_cad.core.model.xdata import get_type, get_uid
from logic_cad.core.text.layout_resolver import normalize_dxf_text_entity
from logic_cad.ui.block_paint import paint_text_path_mm, text_path_bounds_item_local
from logic_cad.ui.bulge_path import append_bulge_arc_to_path
from logic_cad.ui.scene_item.z_order import CANVAS_Z_PASSIVE_DXF_MIRROR
from logic_cad.ui.dxf_display_color import entity_stroke_qcolor
from logic_cad.ui.items.mtext_item import DxfMTextItem
from logic_cad.ui.items.wire_item import apply_dxf_linetype_to_pen, dxf_to_scene

_PASSIVE_DXF_TYPES: frozenset[str] = frozenset({"LINE", "LWPOLYLINE", "ARC", "CIRCLE", "TEXT", "MTEXT"})
_ARC_FLATTEN_MM: float = 0.35


def should_add_passive_primitive(entity: DXFEntity) -> bool:
    """Return True if *entity* should be drawn as a passive item (no LD ``uid``).

    Skips internal layers (same policy as PDF export), duplicate frame/vport polylines,
    and wire-arrow polylines that are already rendered as ``WireArrowItem``.

    Args:
        entity: Entity in the current paper layout block.

    Returns:
        True when this module should add a non-interactive graphics item for *entity*.
    """
    if get_uid(entity):
        return False
    dt = entity.dxftype()
    if dt not in _PASSIVE_DXF_TYPES:
        return False
    layer = str(entity.dxf.layer)
    if is_hidden_for_passive_layout_primitive(layer):
        return False
    if dt == "LWPOLYLINE" and layer in (LAYER_FRAME, LAYER_VPORT):
        return False
    if dt == "LWPOLYLINE" and is_wire_layer(layer) and get_type(entity) == ENTITY_TYPE_WIRE_ARROW:
        return False
    return True


def _entity_linetype(entity: DXFEntity) -> str:
    """Normalize DXF linetype name for dash mapping (default continuous).

    Args:
        entity: Graphic entity with optional ``dxf.linetype``.

    Returns:
        Non-empty linetype string.
    """
    raw = getattr(entity.dxf, "linetype", None)
    s = str(raw).strip() if raw else ""
    return s if s else LINETYPE_CONTINUOUS


def _stroke_pen(doc: Drawing, entity: DXFEntity) -> QPen:
    """Build a cosmetic pen from entity/layer color and linetype.

    Args:
        doc: Drawing for BYLAYER resolution.
        entity: Source graphic.

    Returns:
        Configured cosmetic ``QPen``.
    """
    st = entity_stroke_qcolor(doc, entity)
    pen = QPen(st, 0)
    pen.setCosmetic(True)
    apply_dxf_linetype_to_pen(pen, _entity_linetype(entity))
    return pen


def _path_from_lwpolyline(entity: DXFEntity) -> QPainterPath | None:
    """Tessellate an ``LWPOLYLINE`` (bulges + optional close) into scene space.

    Args:
        entity: ``LWPOLYLINE`` in layout space.

    Returns:
        Scene ``QPainterPath``, or ``None`` if too few vertices.
    """
    rows = list(entity.get_points("xyb"))
    if len(rows) < 2:
        return None
    path = QPainterPath()
    path.moveTo(dxf_to_scene(float(rows[0][0]), float(rows[0][1])))
    for i in range(len(rows) - 1):
        x0 = float(rows[i][0])
        y0 = float(rows[i][1])
        b0 = float(rows[i][2]) if len(rows[i]) > 2 else 0.0
        x1 = float(rows[i + 1][0])
        y1 = float(rows[i + 1][1])
        if abs(b0) < 1e-12:
            path.lineTo(dxf_to_scene(x1, y1))
        else:
            append_bulge_arc_to_path(path, x0, y0, x1, y1, b0)
    if bool(entity.closed):
        path.closeSubpath()
    return path


def _path_from_arc(entity: DXFEntity) -> QPainterPath | None:
    """Flatten a DXF ``ARC`` into a scene-space polyline path.

    Args:
        entity: ``ARC`` entity.

    Returns:
        Scene ``QPainterPath``, or ``None`` if flattening yields no segments.
    """
    c = entity.dxf.center
    arc = ConstructionArc(
        center=(float(c.x), float(c.y)),
        radius=float(entity.dxf.radius),
        start_angle=float(entity.dxf.start_angle),
        end_angle=float(entity.dxf.end_angle),
    )
    pts = list(arc.flattening(_ARC_FLATTEN_MM))
    if len(pts) < 2:
        return None
    path = QPainterPath()
    path.moveTo(dxf_to_scene(float(pts[0].x), float(pts[0].y)))
    for p in pts[1:]:
        path.lineTo(dxf_to_scene(float(p.x), float(p.y)))
    return path


class _PassiveDxfTextItem(QGraphicsItem):
    """Single-line TEXT using the same path outline style as sketch ATTDEF labels."""

    def __init__(
        self,
        doc: Drawing,
        entity: DXFEntity,
        *,
        parent: QGraphicsItem | None = None,
    ) -> None:
        """Build a non-selectable text item from a DXF TEXT entity.

        Args:
            doc: Drawing for BYLAYER stroke resolution.
            entity: Source TEXT entity.
            parent: Optional Qt parent item.
        """
        super().__init__(parent)
        self._layout = normalize_dxf_text_entity(entity)
        self._fill = entity_stroke_qcolor(doc, entity)
        self.setPos(dxf_to_scene(self._layout.anchor_x, self._layout.anchor_y))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)

    def boundingRect(self) -> QRectF:
        """Return bounds of outlined text in item-local coordinates.

        Returns:
            Bounding rectangle for the text path, or a minimal rect when empty.
        """
        r = text_path_bounds_item_local(
            self._layout.text,
            self._layout.height_mm,
            QPointF(0, 0),
            rot_deg=-self._layout.render_rotation_deg,
            halign=self._layout.render_halign,
            valign=self._layout.render_valign,
            width_fac=self._layout.render_width_factor,
            fit_length_mm=self._layout.render_fit_length_mm,
            fit_mode=self._layout.render_fit_mode,
            font_family=self._layout.font_family,
            font_families=self._layout.font_families,
        )
        if r is None or r.isEmpty():
            return QRectF(0, 0, 1, 1)
        return r

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        """Draw path-based text fill.

        Args:
            painter: Active painter.
            option: Style options from the graphics view.
            widget: Optional widget being painted on.

        Returns:
            None
        """
        paint_text_path_mm(
            painter,
            self._layout.text,
            self._layout.height_mm,
            QPointF(0, 0),
            rot_deg=-self._layout.render_rotation_deg,
            halign=self._layout.render_halign,
            valign=self._layout.render_valign,
            width_fac=self._layout.render_width_factor,
            fit_length_mm=self._layout.render_fit_length_mm,
            fit_mode=self._layout.render_fit_mode,
            fill=self._fill,
            font_family=self._layout.font_family,
            font_families=self._layout.font_families,
        )


def add_passive_layout_primitive_items(doc: Drawing, scene: QGraphicsScene, entity: DXFEntity) -> None:
    """If applicable, append passive Qt items to *scene* for *entity*.

    No-op when ``should_add_passive_primitive`` is False or geometry is degenerate.

    Args:
        doc: Active drawing (BYLAYER color resolution).
        scene: Diagram scene receiving items.
        entity: Candidate layout-space entity.

    Returns:
        None
    """
    if not should_add_passive_primitive(entity):
        return
    dt = entity.dxftype()
    if dt == "LINE":
        x0, y0 = float(entity.dxf.start.x), float(entity.dxf.start.y)
        x1, y1 = float(entity.dxf.end.x), float(entity.dxf.end.y)
        p0 = dxf_to_scene(x0, y0)
        p1 = dxf_to_scene(x1, y1)
        ln = QGraphicsLineItem(p0.x(), p0.y(), p1.x(), p1.y())
        ln.setPen(_stroke_pen(doc, entity))
        ln.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        ln.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        ln.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)
        scene.addItem(ln)
        return
    if dt == "LWPOLYLINE":
        path = _path_from_lwpolyline(entity)
        if path is None or path.isEmpty():
            return
        pip = QGraphicsPathItem(path)
        pip.setPen(_stroke_pen(doc, entity))
        pip.setBrush(Qt.BrushStyle.NoBrush)
        pip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        pip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        pip.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)
        scene.addItem(pip)
        return
    if dt == "ARC":
        path = _path_from_arc(entity)
        if path is None or path.isEmpty():
            return
        pip = QGraphicsPathItem(path)
        pip.setPen(_stroke_pen(doc, entity))
        pip.setBrush(Qt.BrushStyle.NoBrush)
        pip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        pip.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        pip.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)
        scene.addItem(pip)
        return
    if dt == "CIRCLE":
        cx, cy = float(entity.dxf.center.x), float(entity.dxf.center.y)
        r = float(entity.dxf.radius)
        top_left = dxf_to_scene(cx - r, cy + r)
        br = QRectF(top_left.x(), top_left.y(), 2 * r, 2 * r)
        el = QGraphicsEllipseItem(br)
        el.setPen(_stroke_pen(doc, entity))
        el.setBrush(Qt.BrushStyle.NoBrush)
        el.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        el.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        el.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)
        scene.addItem(el)
        return
    if dt == "TEXT":
        if not str(getattr(entity.dxf, "text", "") or "").strip():
            return
        scene.addItem(_PassiveDxfTextItem(doc, entity))
        return
    if dt == "MTEXT":
        layout = normalize_dxf_text_entity(entity)
        if not str(layout.text or "").strip():
            return
        it = DxfMTextItem(layout)
        it.setDefaultTextColor(entity_stroke_qcolor(doc, entity))
        it.setZValue(CANVAS_Z_PASSIVE_DXF_MIRROR)
        scene.addItem(it)
        return
