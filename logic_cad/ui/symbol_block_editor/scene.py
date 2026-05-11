"""Graphics scene for editing one block definition (scratch document)."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPainterPathStroker, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QLineEdit,
    QMessageBox,
    QStyle,
    QStyleOptionGraphicsItem,
    QVBoxLayout,
    QWidget,
    QMenu,
)
from ezdxf.document import Drawing
from ezdxf.math import ConstructionArc

from logic_cad.core.attrib_tags import symbol_editor_attdef_tag_choices_unused_in_block
from logic_cad.core.model.constants import (
    BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM,
    BLOCK_EDIT_INITIAL_VIEW_HALF_MM,
    BLOCK_EDIT_MIN_SCENE_HALF_MM,
    ENTITY_TYPE_USER_ARC,
    ENTITY_TYPE_USER_CIRCLE,
    ENTITY_TYPE_USER_LINE,
    GRID_PITCH,
    USER_TEXT_DEFAULT_HEIGHT_MM,
)
from logic_cad.core.model.port_key import parse_port_layer
from logic_cad.core.model.user_sketch_layers import user_sketch_display_linetype_for_entity
from logic_cad.core.model.xdata import get_type, get_uid
from logic_cad.core.services.block_edit_helpers import (
    add_attdef_to_block,
    add_plain_text_to_block,
    add_user_arc_to_block,
    add_user_circle_to_block,
    add_user_line_to_block,
    port_layer_is_taken,
    rotate_scratch_block_entities,
    update_scratch_user_arc_geometry,
    update_scratch_user_circle_geometry,
    update_scratch_user_line_geometry,
)
from logic_cad.core.services.block_edit_session import BlockEditSession
from logic_cad.core.undo.history import find_entity_by_uid
from logic_cad.core.text.layout_resolver import NormalizedTextLayout, normalize_dxf_text_entity
from logic_cad.ui.block_paint import (
    mtext_path_bounds_item_local,
    paint_mtext_path_mm,
    paint_text_path_mm,
    text_path_bounds_item_local,
)
from logic_cad.ui.bulge_path import append_bulge_arc_to_path
from logic_cad.ui.dxf_display_color import entity_effective_linetype, entity_stroke_qcolor
from logic_cad.ui.items.mtext_item import DxfMTextItem
from logic_cad.ui.items.user_geometry_items import UserArcItem, UserCircleItem, UserLineItem
from logic_cad.ui.dialogs.user_text_place_dialog import prompt_dxf_text_string_and_height
from logic_cad.ui.items.wire_item import WIRE_AXIS_HIT_WIDTH_MM, apply_dxf_linetype_to_pen
from logic_cad.ui.passive_dxf_primitives import add_passive_layout_primitive_items, should_add_passive_primitive
from logic_cad.ui.sketch_arc_interaction import (
    arc_vertex_marker_half_mm,
    circle_radius_mm_from_anchor_and_cursor_dxf,
    same_dxf_point,
    try_dxf_arc_through_three_points,
    user_arc_preview_qpainterpath_from_three_points,
)
from logic_cad.ui.snap_utils import (
    dxf_from_scene_pos,
    scene_pos_from_dxf,
    snap_dxf_pos,
    snap_pitch_for_qgraphics_item,
    user_line_end_dxf_from_scene,
)
from logic_cad.ui.view_fit_rect import DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM

_ARC_FLATTEN_MM = 0.35
_PREVIEW_FLAG = 99
_PREVIEW_Z = 10002.0

# Block editor canvas only: glyph substituted for empty default string; DXF ``dxf.text`` stays empty.
_BLOCK_EDIT_ATTDEF_EMPTY_DISPLAY_PLACEHOLDER = "\u25af"

ITEM_KIND_PORT = "PORT"


def _prompt_new_block_attdef(
    parent: QWidget | None, block, *, block_name: str = ""
) -> tuple[str, str] | None:
    """Modal dialog: tag from SYM / LABEL* / STATIC_LABEL* combo + default text."""

    choices = symbol_editor_attdef_tag_choices_unused_in_block(block, block_name=block_name)
    if not choices:
        QMessageBox.warning(
            parent,
            "ATTDEF を配置",
            "配置可能なタグがありません（定義済みのタグはすべてこのブロック内に ATTDEF として存在します）。",
        )
        return None
    dlg = QDialog(parent)
    dlg.setWindowTitle("ATTDEF を配置")
    layout = QVBoxLayout(dlg)
    form = QFormLayout()
    tag_c = QComboBox()
    tag_c.setEditable(False)
    for t in choices:
        tag_c.addItem(t)
    default_ed = QLineEdit()
    form.addRow("タグ", tag_c)
    form.addRow("既定テキスト", default_ed)
    layout.addLayout(form)
    buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
    )
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    layout.addWidget(buttons)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        return None
    tag = str(tag_c.currentText()).strip()
    if not tag:
        return None
    return tag, default_ed.text()


ITEM_KIND_GEOM = "GEOM"
ITEM_KIND_ATTDEF = "ATTDEF"
ITEM_KIND_BLOCK_TEXT = "BLOCK_TEXT"
ITEM_KIND_BLOCK_MTEXT = "BLOCK_MTEXT"

PORT_LAYER_TAKEN_MESSAGE = "その LD_PORT レイヤは既に使用されています。"

# ATTDEF/port commits ignore phantom Qt ItemChange notifications unless pointer-drag snapshot moves.
_BLOCK_EDIT_DRAG_COMMIT_EPS_SCENE_MM = 1e-5


def _dxf_to_scene_pt(x: float, y: float) -> QPointF:
    return scene_pos_from_dxf(x, y)


def _mark_preview_item(it: QGraphicsItem) -> None:
    it.setData(_PREVIEW_FLAG, True)
    it.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


class PortMarkerItem(QGraphicsEllipseItem):
    """Port POINT on canvas; ``pos()`` is grid-snapped during drag."""

    def __init__(self, *args, parent=None) -> None:
        super().__init__(*args, parent)
        self._pm_moved = False
        # DXF sync must not snap; interactive moves snap in ``itemChange``.
        self._programmatic_pos_depth: int = 0

    def place_at_dxf_mm(self, x_mm: float, y_mm: float) -> None:
        """Set scene position from DXF mm without grid snapping (session rebuild)."""
        self._programmatic_pos_depth += 1
        try:
            self.setPos(_dxf_to_scene_pt(float(x_mm), float(y_mm)))
        finally:
            self._programmatic_pos_depth -= 1
        self._pm_moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF) and self._programmatic_pos_depth <= 0:
                xd, yd = dxf_from_scene_pos(value)
                sx, sy = snap_dxf_pos(xd, yd, pitch=snap_pitch_for_qgraphics_item(self))
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._programmatic_pos_depth <= 0:
                self._pm_moved = True
        return super().itemChange(change, value)


class BlockGeomLineItem(QGraphicsLineItem):
    """Native LINE in block; whole segment translates with grid-snapped ``pos()``."""

    def __init__(self, *args, parent=None) -> None:
        super().__init__(*args, parent)
        self._geom_moved = False

    def shape(self) -> QPainterPath:
        """Pick corridor like user lines / wires (± half ``WIRE_AXIS_HIT_WIDTH_MM`` from axis)."""
        ln = self.line()
        path = QPainterPath()
        path.moveTo(ln.p1())
        path.lineTo(ln.p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(WIRE_AXIS_HIT_WIDTH_MM)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(path)

    def boundingRect(self) -> QRectF:
        s = self.shape()
        if s.isEmpty():
            return super().boundingRect()
        return s.boundingRect()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                sx, sy = snap_dxf_pos(xd, yd, pitch=snap_pitch_for_qgraphics_item(self))
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._geom_moved = True
        return super().itemChange(change, value)


class BlockGeomCircleItem(QGraphicsEllipseItem):
    """Native CIRCLE (non-USER); translates with grid-snapped ``pos()``."""

    def __init__(self, *args, parent=None) -> None:
        super().__init__(*args, parent)
        self._geom_moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                sx, sy = snap_dxf_pos(xd, yd, pitch=snap_pitch_for_qgraphics_item(self))
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._geom_moved = True
        return super().itemChange(change, value)


class BlockGeomLwPolyItem(QGraphicsPathItem):
    """LWPOLYLINE from DXF; translation preserves bulge values via stored vertices."""

    def __init__(self, path: QPainterPath, *, rows_xyb: list[tuple[float, float, float]], closed: bool, parent=None) -> None:
        super().__init__(path, parent)
        self._ld_rows_xyb = rows_xyb
        self._ld_closed = closed
        self._geom_moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF):
                xd, yd = dxf_from_scene_pos(value)
                sx, sy = snap_dxf_pos(xd, yd, pitch=snap_pitch_for_qgraphics_item(self))
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._geom_moved = True
        return super().itemChange(change, value)


def _attdef_empty_default_shows_placeholder(ent: Any) -> bool:
    """Return True when the ATTDEF default string is empty or whitespace-only.

    The block editor then draws ``_BLOCK_EDIT_ATTDEF_EMPTY_DISPLAY_PLACEHOLDER`` without
    changing stored DXF text.

    Args:
        ent: DXF ATTDEF entity.

    Returns:
        Whether to substitute the placeholder glyph for layout and paint.
    """
    return not str(getattr(ent.dxf, "text", None) or "").strip()


class AttdefEditItem(QGraphicsItem):
    """Block-local ATTDEF: Qt item tracks DXF insert; alignment stays on the entity."""

    def __init__(
        self,
        get_session: Callable[[], BlockEditSession | None],
        block_handle: str,
        *,
        snap_pitch_mm: Callable[[], float],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._get_session = get_session
        self._snap_pitch_mm = snap_pitch_mm
        self._handle = str(block_handle)
        self.setData(0, self._handle)
        self.setData(1, ITEM_KIND_ATTDEF)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(45)
        self._moved = False
        self._programmatic_pos_depth: int = 0

    def _entity(self):
        session = self._get_session()
        if session is None:
            return None
        blk = session.scratch_block()
        if blk is None:
            return None
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == self._handle:
                return e
        return None

    def sync_pos_from_entity(self) -> None:
        """Place the item at the normalized render anchor for the current ATTDEF.

        Uses programmatic positioning so ``itemChange`` grid snapping does not
        round DXF-backed coordinates when rebuilding from the scratch session.
        """
        ent = self._entity()
        if ent is None or ent.dxftype() != "ATTDEF":
            return
        lay = normalize_dxf_text_entity(ent)
        self._programmatic_pos_depth += 1
        try:
            self.setPos(_dxf_to_scene_pt(lay.anchor_x, lay.anchor_y))
        finally:
            self._programmatic_pos_depth -= 1
        self._moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF) and self._programmatic_pos_depth <= 0:
                xd, yd = dxf_from_scene_pos(value)
                pitch = float(self._snap_pitch_mm())
                sx, sy = snap_dxf_pos(xd, yd, pitch=pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._programmatic_pos_depth <= 0:
                self._moved = True
        return super().itemChange(change, value)

    def _layout_live(self):
        """Normalized layout with insert/anchor matching the current item position (smooth drag)."""
        ent = self._entity()
        if ent is None or ent.dxftype() != "ATTDEF":
            return None
        lay0 = normalize_dxf_text_entity(ent)
        ix, iy = dxf_from_scene_pos(self.pos())
        text = (
            _BLOCK_EDIT_ATTDEF_EMPTY_DISPLAY_PLACEHOLDER
            if _attdef_empty_default_shows_placeholder(ent)
            else lay0.text
        )
        return replace(lay0, insert_x=ix, insert_y=iy, anchor_x=ix, anchor_y=iy, text=text)

    def boundingRect(self) -> QRectF:
        lay = self._layout_live()
        if lay is None:
            return QRectF(0, 0, 1, 1)
        r = text_path_bounds_item_local(
            lay.text,
            lay.height_mm,
            QPointF(0, 0),
            rot_deg=-lay.render_rotation_deg,
            halign=lay.render_halign,
            valign=lay.render_valign,
            width_fac=lay.render_width_factor,
            fit_length_mm=lay.render_fit_length_mm,
            fit_mode=lay.render_fit_mode,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if r is None or r.isEmpty():
            return QRectF(0, 0, 1, 1)
        return r

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        lay = self._layout_live()
        if lay is None:
            return
        ent = self._entity()
        fill = (
            QColor(130, 135, 145)
            if ent is not None and _attdef_empty_default_shows_placeholder(ent)
            else QColor(200, 200, 210)
        )
        paint_text_path_mm(
            painter,
            lay.text,
            lay.height_mm,
            QPointF(0, 0),
            rot_deg=-lay.render_rotation_deg,
            halign=lay.render_halign,
            valign=lay.render_valign,
            width_fac=lay.render_width_factor,
            fit_length_mm=lay.render_fit_length_mm,
            fit_mode=lay.render_fit_mode,
            fill=fill,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


class BlockTextEditItem(QGraphicsItem):
    """Block ``TEXT`` entity: Qt position tracks DXF insert / render anchor."""

    def __init__(
        self,
        get_session: Callable[[], BlockEditSession | None],
        block_handle: str,
        *,
        snap_pitch_mm: Callable[[], float],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._get_session = get_session
        self._snap_pitch_mm = snap_pitch_mm
        self._handle = str(block_handle)
        self.setData(0, self._handle)
        self.setData(1, ITEM_KIND_BLOCK_TEXT)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(45)
        self._moved = False
        self._programmatic_pos_depth: int = 0

    def _entity(self):
        session = self._get_session()
        if session is None:
            return None
        blk = session.scratch_block()
        if blk is None:
            return None
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == self._handle:
                return e
        return None

    def sync_pos_from_entity(self) -> None:
        """Place at normalized anchor for the current ``TEXT`` (no grid rounding)."""

        ent = self._entity()
        if ent is None or ent.dxftype() != "TEXT":
            return
        lay = normalize_dxf_text_entity(ent)
        self._programmatic_pos_depth += 1
        try:
            self.setPos(_dxf_to_scene_pt(lay.anchor_x, lay.anchor_y))
        finally:
            self._programmatic_pos_depth -= 1
        self._moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF) and self._programmatic_pos_depth <= 0:
                xd, yd = dxf_from_scene_pos(value)
                pitch = float(self._snap_pitch_mm())
                sx, sy = snap_dxf_pos(xd, yd, pitch=pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._programmatic_pos_depth <= 0:
                self._moved = True
        return super().itemChange(change, value)

    def _layout_live(self) -> NormalizedTextLayout | None:
        ent = self._entity()
        if ent is None or ent.dxftype() != "TEXT":
            return None
        lay0 = normalize_dxf_text_entity(ent)
        ix, iy = dxf_from_scene_pos(self.pos())
        return replace(lay0, insert_x=ix, insert_y=iy, anchor_x=ix, anchor_y=iy)

    def boundingRect(self) -> QRectF:
        lay = self._layout_live()
        if lay is None:
            return QRectF(0, 0, 1, 1)
        r = text_path_bounds_item_local(
            lay.text,
            lay.height_mm,
            QPointF(0, 0),
            rot_deg=-lay.render_rotation_deg,
            halign=lay.render_halign,
            valign=lay.render_valign,
            width_fac=lay.render_width_factor,
            fit_length_mm=lay.render_fit_length_mm,
            fit_mode=lay.render_fit_mode,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if r is None or r.isEmpty():
            return QRectF(0, 0, 1, 1)
        return r

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        lay = self._layout_live()
        if lay is None:
            return
        paint_text_path_mm(
            painter,
            lay.text,
            lay.height_mm,
            QPointF(0, 0),
            rot_deg=-lay.render_rotation_deg,
            halign=lay.render_halign,
            valign=lay.render_valign,
            width_fac=lay.render_width_factor,
            fit_length_mm=lay.render_fit_length_mm,
            fit_mode=lay.render_fit_mode,
            fill=QColor(200, 200, 210),
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


class BlockMTextEditItem(DxfMTextItem):
    """Editable ``MTEXT`` inside a block (path rendering + drag + property edits)."""

    def __init__(
        self,
        get_session: Callable[[], BlockEditSession | None],
        block_handle: str,
        snap_pitch_mm: Callable[[], float],
        entity,
    ) -> None:
        lay = normalize_dxf_text_entity(entity)
        super().__init__(lay)
        self._get_session = get_session
        self._snap_pitch_mm = snap_pitch_mm
        self._handle = str(block_handle)
        self._moved = False
        self._programmatic_pos_depth: int = 0
        self.setData(0, self._handle)
        self.setData(1, ITEM_KIND_BLOCK_MTEXT)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(45)

    def _entity(self):
        session = self._get_session()
        if session is None:
            return None
        blk = session.scratch_block()
        if blk is None:
            return None
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == self._handle:
                return e
        return None

    def sync_pos_from_entity(self) -> None:
        ent = self._entity()
        if ent is None or ent.dxftype() != "MTEXT":
            return
        lay = normalize_dxf_text_entity(ent)
        self._layout = lay
        br = mtext_path_bounds_item_local(
            lay.text,
            lay.height_mm,
            width_mm=lay.width_mm,
            line_gap_ratio=self._line_gap_ratio,
            halign=lay.halign,
            valign=lay.valign,
            width_fac=lay.width_factor,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        self._bounds = br if br is not None and not br.isEmpty() else QRectF(-0.5, -0.5, 1.0, 1.0)
        self._programmatic_pos_depth += 1
        try:
            self.setPos(_dxf_to_scene_pt(lay.anchor_x, lay.anchor_y))
            self.setRotation(-float(lay.rotation_deg))
        finally:
            self._programmatic_pos_depth -= 1
        self._moved = False

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            if isinstance(value, QPointF) and self._programmatic_pos_depth <= 0:
                xd, yd = dxf_from_scene_pos(value)
                pitch = float(self._snap_pitch_mm())
                sx, sy = snap_dxf_pos(xd, yd, pitch=pitch)
                value = scene_pos_from_dxf(sx, sy)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if self._programmatic_pos_depth <= 0:
                self._moved = True
        return super().itemChange(change, value)

    def _layout_live(self) -> NormalizedTextLayout | None:
        ent = self._entity()
        if ent is None or ent.dxftype() != "MTEXT":
            return None
        lay0 = normalize_dxf_text_entity(ent)
        ix, iy = dxf_from_scene_pos(self.pos())
        return replace(lay0, insert_x=ix, insert_y=iy, anchor_x=ix, anchor_y=iy)

    def boundingRect(self) -> QRectF:
        lay = self._layout_live()
        if lay is None:
            return super().boundingRect()
        br = mtext_path_bounds_item_local(
            lay.text,
            lay.height_mm,
            width_mm=lay.width_mm,
            line_gap_ratio=self._line_gap_ratio,
            halign=lay.halign,
            valign=lay.valign,
            width_fac=lay.width_factor,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if br is None or br.isEmpty():
            return QRectF(-0.5, -0.5, 1.0, 1.0)
        return br

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget | None = None) -> None:
        lay = self._layout_live()
        if lay is None:
            return
        paint_mtext_path_mm(
            painter,
            lay.text,
            lay.height_mm,
            QPointF(0.0, 0.0),
            width_mm=lay.width_mm,
            line_gap_ratio=self._line_gap_ratio,
            halign=lay.halign,
            valign=lay.valign,
            width_fac=lay.width_factor,
            fill=self._color,
            font_family=lay.font_family,
            font_families=lay.font_families,
        )
        if option.state & QStyle.StateFlag.State_Selected:
            p = QPen(QColor(90, 170, 255), 0)
            p.setCosmetic(True)
            p.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(p)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.boundingRect())


class SymbolBlockEditScene(QGraphicsScene):
    """Block geometry + user sketch on ``LD_SYMBOL``; ports; ATTDEF on ``LD_TEXT``."""

    edited = Signal()
    status_message = Signal(str)

    def __init__(
        self,
        get_session: Callable[[], BlockEditSession | None],
        request_port_layer: Callable[[], str | None],
        sketch_line_linetype: Callable[[], str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._get_session = get_session
        self._request_port_layer = request_port_layer
        self._sketch_line_linetype = sketch_line_linetype
        self._placement: str | None = None
        self._line_p0_dxf: tuple[float, float] | None = None
        self._circle_c_dxf: tuple[float, float] | None = None
        self._sketch_preview_line: QGraphicsLineItem | None = None
        self._sketch_preview_circle: QGraphicsEllipseItem | None = None
        self._sketch_arc_dxf_pts: list[tuple[float, float]] = []
        self._sketch_preview_arc: QGraphicsPathItem | None = None
        self._sketch_preview_arc_chord: QGraphicsLineItem | None = None
        self._sketch_preview_arc_markers: list[QGraphicsRectItem] = []
        self._preview_port: QGraphicsEllipseItem | None = None
        self._user_line_endpoint_drag: tuple[UserLineItem, int] | None = None
        self._drag_start_scene: dict[int, QPointF] | None = None
        self._auxiliary_snap_pitch_mm: float = float(BLOCK_EDIT_AUX_GRID_DEFAULT_PITCH_MM)
        self.snap_pitch_mm: float = float(GRID_PITCH)
        self._auxiliary_grid_visible: bool = False

    def set_auxiliary_snap_pitch_mm(self, pitch_mm: float) -> None:
        """Update auxiliary pitch used when minor grid is visible."""
        pitch = float(pitch_mm)
        if pitch <= 1e-12:
            return
        if abs(self._auxiliary_snap_pitch_mm - pitch) <= 1e-12:
            return
        self._auxiliary_snap_pitch_mm = pitch
        if self._auxiliary_grid_visible:
            self.set_auxiliary_grid_visible(True)

    def set_auxiliary_grid_visible(self, visible: bool) -> None:
        """Show or hide the fine subdivision grid and synchronize snap pitch.

        Major 1 mm grid, scene fill, and origin marker remain. When the auxiliary
        grid is hidden, snapping falls back to the 1 mm major grid so the visual
        state and snapping behavior stay aligned.

        Args:
            visible: If True, draw minor grid lines and use minor snap pitch;
                if False, draw only major grid lines and snap at 1 mm.
        """
        v = bool(visible)
        next_snap = self._auxiliary_snap_pitch_mm if v else float(GRID_PITCH)
        snap_changed = abs(self.snap_pitch_mm - next_snap) > 1e-12
        if self._auxiliary_grid_visible == v and not snap_changed:
            return
        self._auxiliary_grid_visible = v
        self.snap_pitch_mm = next_snap
        # ``invalidate(BackgroundLayer)`` alone is skipped on some platforms; force scene + view repaint.
        sr = self.sceneRect()
        if sr.isValid() and not sr.isEmpty():
            self.update(sr)
        else:
            self.update()
        for view in self.views():
            view.update()
            vp = view.viewport()
            if vp is not None:
                vp.update()

    def length_hud_mm(self) -> float | None:
        """USER_LINE endpoint drag or line placement preview length (scene mm)."""

        if self._user_line_endpoint_drag is not None:
            li, _ = self._user_line_endpoint_drag
            (x0, y0), (x1, y1) = li.line_endpoints_dxf()
            return float(math.hypot(x1 - x0, y1 - y0))
        if (
            self._placement == "line"
            and self._line_p0_dxf is not None
            and self._sketch_preview_line is not None
        ):
            ln = self._sketch_preview_line.line()
            return float(math.hypot(ln.x2() - ln.x1(), ln.y2() - ln.y1()))
        return None

    def _reset_line_draft(self) -> None:
        self._line_p0_dxf = None
        if self._sketch_preview_line is not None:
            self.removeItem(self._sketch_preview_line)
            self._sketch_preview_line = None

    def _reset_circle_draft(self) -> None:
        self._circle_c_dxf = None
        if self._sketch_preview_circle is not None:
            self.removeItem(self._sketch_preview_circle)
            self._sketch_preview_circle = None

    def _reset_arc_draft(self) -> None:
        self._sketch_arc_dxf_pts.clear()
        if self._sketch_preview_arc is not None:
            self.removeItem(self._sketch_preview_arc)
            self._sketch_preview_arc = None
        if self._sketch_preview_arc_chord is not None:
            self.removeItem(self._sketch_preview_arc_chord)
            self._sketch_preview_arc_chord = None
        for mr in self._sketch_preview_arc_markers:
            self.removeItem(mr)
        self._sketch_preview_arc_markers.clear()

    def placement_preview_in_progress(self) -> bool:
        """Return True while line/circle/arc placement has started but not committed.

        Used for Escape handling: first Esc clears this preview only; second Esc clears the tool.

        Returns:
            True when a placement rubber-band or arc chord step is active.
        """

        if self._placement == "line" and self._line_p0_dxf is not None:
            return True
        if self._placement == "circle" and self._circle_c_dxf is not None:
            return True
        if self._placement == "arc" and len(self._sketch_arc_dxf_pts) > 0:
            return True
        return False

    def cancel_placement_preview_keep_tool(self) -> None:
        """Discard line/circle/arc placement previews without changing the active tool.

        Clears draft geometry only (same outcome as right-click cancel on those tools).

        Returns:
            None
        """

        self._reset_line_draft()
        self._reset_circle_draft()
        self._reset_arc_draft()

    def _ensure_port_hover(self, scene_pos: QPointF) -> None:
        if self._placement != "port":
            return
        x, y = snap_dxf_pos(*dxf_from_scene_pos(scene_pos), pitch=self.snap_pitch_mm)
        p = _dxf_to_scene_pt(x, y)
        if self._preview_port is None:
            el = QGraphicsEllipseItem(-0.45, -0.45, 0.9, 0.9)
            pen = QPen(QColor(140, 230, 150, 200))
            pen.setCosmetic(True)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            el.setPen(pen)
            el.setBrush(QColor(140, 230, 150, 35))
            el.setZValue(_PREVIEW_Z)
            _mark_preview_item(el)
            self.addItem(el)
            self._preview_port = el
        self._preview_port.setPos(p)

    def _hide_port_hover(self) -> None:
        if self._preview_port is not None:
            self.removeItem(self._preview_port)
            self._preview_port = None

    def _circle_radius_mm(self, center: tuple[float, float], scene_pos: QPointF) -> float:
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos), pitch=self.snap_pitch_mm)
        return circle_radius_mm_from_anchor_and_cursor_dxf(
            center, (tx, ty), snap_pitch_mm=float(self.snap_pitch_mm)
        )

    def _update_line_preview(self, scene_pos: QPointF, modifiers: Qt.KeyboardModifier) -> None:
        if self._sketch_preview_line is None or self._line_p0_dxf is None:
            return
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        p1 = user_line_end_dxf_from_scene(self._line_p0_dxf, scene_pos, shift, pitch=self.snap_pitch_mm)
        p0s = _dxf_to_scene_pt(*self._line_p0_dxf)
        p1s = _dxf_to_scene_pt(*p1)
        self._sketch_preview_line.setLine(p0s.x(), p0s.y(), p1s.x(), p1s.y())

    def _update_circle_preview(self, scene_pos: QPointF) -> None:
        if self._sketch_preview_circle is None or self._circle_c_dxf is None:
            return
        r = self._circle_radius_mm(self._circle_c_dxf, scene_pos)
        cx, cy = self._circle_c_dxf
        tl = _dxf_to_scene_pt(cx - r, cy + r)
        self._sketch_preview_circle.setRect(tl.x(), tl.y(), 2 * r, 2 * r)

    def _update_arc_preview(self, scene_pos: QPointF) -> None:
        if self._sketch_preview_arc is None or len(self._sketch_arc_dxf_pts) != 2:
            return
        p0, p1 = self._sketch_arc_dxf_pts[0], self._sketch_arc_dxf_pts[1]
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos), pitch=self.snap_pitch_mm)
        path = user_arc_preview_qpainterpath_from_three_points(p0, p1, (tx, ty))
        if path is None:
            self._sketch_preview_arc.setPath(QPainterPath())
            return
        self._sketch_preview_arc.setPath(path)

    def _clear_arc_placement_markers_only(self) -> None:
        for mr in self._sketch_preview_arc_markers:
            self.removeItem(mr)
        self._sketch_preview_arc_markers.clear()

    def _update_arc_chord_rubber(self, scene_pos: QPointF) -> None:
        if self._sketch_preview_arc_chord is None or len(self._sketch_arc_dxf_pts) != 1:
            return
        p0 = self._sketch_arc_dxf_pts[0]
        tx, ty = snap_dxf_pos(*dxf_from_scene_pos(scene_pos), pitch=self.snap_pitch_mm)
        p0s = _dxf_to_scene_pt(*p0)
        p1s = _dxf_to_scene_pt(tx, ty)
        self._sketch_preview_arc_chord.setLine(p0s.x(), p0s.y(), p1s.x(), p1s.y())

    def _add_arc_locked_vertex_markers(self) -> None:
        self._clear_arc_placement_markers_only()
        if len(self._sketch_arc_dxf_pts) < 2:
            return
        half = arc_vertex_marker_half_mm(float(self.snap_pitch_mm))
        for x, y in self._sketch_arc_dxf_pts[:2]:
            mr = QGraphicsRectItem(-half, -half, 2.0 * half, 2.0 * half)
            mr.setBrush(QColor(100, 180, 220))
            mr.setPen(Qt.PenStyle.NoPen)
            mr.setZValue(_PREVIEW_Z + 0.5)
            _mark_preview_item(mr)
            ps = _dxf_to_scene_pt(x, y)
            mr.setPos(ps)
            self.addItem(mr)
            self._sketch_preview_arc_markers.append(mr)

    def set_placement_tool(self, name: str | None) -> None:
        """``None`` = navigate / select / move (like main canvas)."""
        key = None if name is None or str(name) in ("", "select", "nav") else str(name)
        self._user_line_endpoint_drag = None
        self._placement = key
        if key != "line":
            self._reset_line_draft()
        if key != "circle":
            self._reset_circle_draft()
        if key != "arc":
            self._reset_arc_draft()
        if key != "port":
            self._hide_port_hover()
        self._apply_interaction_flags()

    def set_tool(self, name: str) -> None:
        """Backward-compatible alias for :meth:`set_placement_tool`."""
        self.set_placement_tool(None if name in ("select", "nav", "") else str(name))

    def _apply_interaction_flags(self) -> None:
        for it in self.items():
            if it.data(_PREVIEW_FLAG):
                continue
            kind = str(it.data(1) or "")
            if kind == ITEM_KIND_PORT:
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            elif kind == ITEM_KIND_GEOM:
                movable = isinstance(it, BlockGeomLineItem | BlockGeomCircleItem | BlockGeomLwPolyItem)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
            elif kind == ITEM_KIND_ATTDEF:
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            elif kind in (ITEM_KIND_BLOCK_TEXT, ITEM_KIND_BLOCK_MTEXT):
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
            elif isinstance(it, UserLineItem | UserCircleItem | UserArcItem):
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)

    def extent_rect_for_view_fit(self) -> QRectF:
        """Rectangle for middle-double-click ``fitInView``.

        Uses padded item bounds when present; otherwise a margin around
        :meth:`initial_view_scene_rect` (no ±250 mm scroll-range floor).

        Returns:
            Scene-axis-aligned rectangle in millimetres suitable for ``fitInView``.
        """

        pad = float(DEFAULT_DIAGRAM_VIEW_FIT_MARGIN_MM)
        br = self.itemsBoundingRect()
        if br.isValid() and not br.isEmpty():
            return br.adjusted(-pad, -pad, pad, pad)
        return self.initial_view_scene_rect().adjusted(-pad, -pad, pad, pad)

    def initial_view_scene_rect(self) -> QRectF:
        """Frame for default zoom-on-open around insertion origin (± mm per axis in scene space)."""
        half = float(BLOCK_EDIT_INITIAL_VIEW_HALF_MM)
        return QRectF(-half, -half, 2 * half, 2 * half)

    def _is_rotatable_item(self, it: QGraphicsItem) -> bool:
        if it.data(_PREVIEW_FLAG):
            return False
        if isinstance(it, (UserLineItem, UserCircleItem, UserArcItem)):
            return True
        kind = str(it.data(1) or "")
        h = str(it.data(0) or "")
        return bool(h) and kind in (
            ITEM_KIND_PORT,
            ITEM_KIND_GEOM,
            ITEM_KIND_ATTDEF,
            ITEM_KIND_BLOCK_TEXT,
            ITEM_KIND_BLOCK_MTEXT,
        )

    def _append_item_rotate_ids(self, it: QGraphicsItem, handles: set[str], uids: set[str]) -> None:
        if isinstance(it, UserLineItem):
            uids.add(it.sketch_uid)
            return
        if isinstance(it, UserCircleItem):
            uids.add(it.sketch_uid)
            return
        if isinstance(it, UserArcItem):
            uids.add(it.sketch_uid)
            return
        h = str(it.data(0) or "")
        kind = str(it.data(1) or "")
        if h and kind in (
            ITEM_KIND_PORT,
            ITEM_KIND_GEOM,
            ITEM_KIND_ATTDEF,
            ITEM_KIND_BLOCK_TEXT,
            ITEM_KIND_BLOCK_MTEXT,
        ):
            handles.add(h)

    def _collect_rotate_targets(
        self, scene_pos: QPointF, device_transform
    ) -> tuple[set[str], set[str]] | None:
        handles: set[str] = set()
        uids: set[str] = set()
        selected = [it for it in self.selectedItems() if self._is_rotatable_item(it)]
        if selected:
            for it in selected:
                self._append_item_rotate_ids(it, handles, uids)
        else:
            items = self.items(
                scene_pos,
                Qt.ItemSelectionMode.IntersectsItemShape,
                Qt.SortOrder.DescendingOrder,
                device_transform,
            )
            top = items[0] if items else None
            if top is None or not self._is_rotatable_item(top):
                return None
            self._append_item_rotate_ids(top, handles, uids)
        if not handles and not uids:
            return None
        return handles, uids

    def deliver_context_menu(
        self,
        scene_pos: QPointF,
        screen_global_pos,
        view_widget: QWidget,
        device_transform,
    ) -> bool:
        session = self._get_session()
        if session is None:
            return False
        targets = self._collect_rotate_targets(scene_pos, device_transform)
        if targets is None:
            return False
        handles, uids = targets
        menu = QMenu(view_widget)
        a_cw = menu.addAction("90° 回転（時計回り）")
        a_ccw = menu.addAction("90° 回転（反時計回り）")
        chosen = menu.exec(screen_global_pos)
        if chosen not in (a_cw, a_ccw):
            return True
        delta = -90 if chosen == a_cw else 90
        self._apply_rotate(delta, frozenset(handles), frozenset(uids))
        return True

    def _apply_rotate(self, delta_deg: int, handles: frozenset[str], uids: frozenset[str]) -> None:
        session = self._get_session()
        if session is None:
            return
        blk = session.scratch_block()
        if blk is None:
            return
        with session.begin("block_edit_rotate"):
            rotate_scratch_block_entities(
                blk,
                session.scratch_doc,
                delta_deg=float(delta_deg),
                handles=handles,
                sketch_uids=uids,
            )
        self.refresh_from_session()
        self.edited.emit()

    def drawBackground(self, painter, rect) -> None:
        painter.fillRect(rect, QColor(34, 36, 40))
        major = float(GRID_PITCH)
        margin = major * 2
        left, top = rect.left() - margin, rect.top() - margin
        right, bottom = rect.right() + margin, rect.bottom() + margin
        if self._auxiliary_grid_visible:
            minor = float(self._auxiliary_snap_pitch_mm)
            steps = int(round(major / minor)) if minor > 1e-12 else 1
            if steps > 1:
                minor_pen = QPen(QColor(86, 96, 114))
                minor_pen.setCosmetic(True)
                painter.setPen(minor_pen)
                i0 = int(math.floor(left / minor))
                i1 = int(math.ceil(right / minor))
                for i in range(i0, i1 + 1):
                    if i % steps == 0:
                        continue
                    x = i * minor
                    painter.drawLine(x, top, x, bottom)
                j0 = int(math.floor(top / minor))
                j1 = int(math.ceil(bottom / minor))
                for j in range(j0, j1 + 1):
                    if j % steps == 0:
                        continue
                    y = j * minor
                    painter.drawLine(left, y, right, y)
        pen = QPen(QColor(55, 58, 64))
        pen.setCosmetic(True)
        painter.setPen(pen)
        xi0 = int(math.floor(left / major))
        xi1 = int(math.ceil(right / major))
        for i in range(xi0, xi1 + 1):
            x = i * major
            painter.drawLine(x, top, x, bottom)
        j0 = int(math.floor(top / major))
        j1 = int(math.ceil(bottom / major))
        for j in range(j0, j1 + 1):
            y = j * major
            painter.drawLine(left, y, right, y)
        # Block insertion origin (DXF 0,0) — subtle crosshair only.
        arm = GRID_PITCH * 3.0
        ori_pen = QPen(QColor(120, 125, 135, 180))
        ori_pen.setCosmetic(True)
        ori_pen.setWidth(1)
        painter.setPen(ori_pen)
        painter.drawLine(QPointF(-arm, 0), QPointF(arm, 0))
        painter.drawLine(QPointF(0, -arm), QPointF(0, arm))
        ring_pen = QPen(QColor(100, 110, 125, 130))
        ring_pen.setCosmetic(True)
        ring_pen.setWidth(1)
        painter.setPen(ring_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QPointF(0, 0), 0.65, 0.65)

    def refresh_from_session(self) -> None:
        self._user_line_endpoint_drag = None
        self._reset_line_draft()
        self._reset_circle_draft()
        self._hide_port_hover()
        session = self._get_session()
        if session is None:
            self.clear()
            return
        blk = session.scratch_block()
        if blk is None:
            self.clear()
            return
        self._rebuild(blk, session.scratch_doc)

    def _tag_geom_arc_item(self, it: QGraphicsItem, handle: str) -> None:
        """Flattened ARC path: keep fixed (re-approximating arcs on move is skipped)."""
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        it.setData(0, handle)
        it.setData(1, ITEM_KIND_GEOM)

    def _tag_movable_geom_line(self, it: BlockGeomLineItem, handle: str) -> None:
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        it.setData(0, handle)
        it.setData(1, ITEM_KIND_GEOM)

    def _tag_movable_geom_circle(self, it: BlockGeomCircleItem, handle: str) -> None:
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        it.setData(0, handle)
        it.setData(1, ITEM_KIND_GEOM)

    def _tag_movable_geom_lwpoly(self, it: BlockGeomLwPolyItem, handle: str) -> None:
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        it.setData(0, handle)
        it.setData(1, ITEM_KIND_GEOM)

    def _rebuild(self, block, doc: Drawing) -> None:
        pl = self._placement
        self.clear()
        self._placement = pl
        self._sketch_preview_line = None
        self._sketch_preview_circle = None
        self._sketch_preview_arc = None
        self._sketch_preview_arc_chord = None
        self._sketch_preview_arc_markers.clear()
        self._sketch_arc_dxf_pts.clear()
        self._preview_port = None
        for entity in block:
            et = entity.dxftype()
            handle = str(getattr(entity.dxf, "handle", "") or "")
            if et == "LINE":
                uid = get_uid(entity)
                if uid and get_type(entity) == ENTITY_TYPE_USER_LINE:
                    x0, y0 = float(entity.dxf.start.x), float(entity.dxf.start.y)
                    x1, y1 = float(entity.dxf.end.x), float(entity.dxf.end.y)
                    lt = user_sketch_display_linetype_for_entity(entity)
                    st = entity_stroke_qcolor(doc, entity)
                    ul = UserLineItem(uid, x0, y0, x1, y1, linetype=lt, stroke_color=st)
                    ul.setZValue(40)
                    self.addItem(ul)
                    continue
                if not uid and should_add_passive_primitive(entity):
                    add_passive_layout_primitive_items(doc, self, entity)
                    continue
                x0, y0 = float(entity.dxf.start.x), float(entity.dxf.start.y)
                x1, y1 = float(entity.dxf.end.x), float(entity.dxf.end.y)
                p0, p1 = _dxf_to_scene_pt(x0, y0), _dxf_to_scene_pt(x1, y1)
                ln = BlockGeomLineItem(p0.x(), p0.y(), p1.x(), p1.y())
                pen = QPen(entity_stroke_qcolor(doc, entity), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, entity_effective_linetype(doc, entity))
                ln.setPen(pen)
                self._tag_movable_geom_line(ln, handle)
                ln.setZValue(0)
                self.addItem(ln)
            elif et == "CIRCLE":
                uid = get_uid(entity)
                if uid and get_type(entity) == ENTITY_TYPE_USER_CIRCLE:
                    cx, cy = float(entity.dxf.center.x), float(entity.dxf.center.y)
                    r = float(entity.dxf.radius)
                    lt = user_sketch_display_linetype_for_entity(entity)
                    st = entity_stroke_qcolor(doc, entity)
                    uc = UserCircleItem(uid, cx, cy, r, linetype=lt, stroke_color=st)
                    uc.setZValue(40)
                    self.addItem(uc)
                    continue
                if not uid and should_add_passive_primitive(entity):
                    add_passive_layout_primitive_items(doc, self, entity)
                    continue
                cx, cy = float(entity.dxf.center.x), float(entity.dxf.center.y)
                r = float(entity.dxf.radius)
                tl = _dxf_to_scene_pt(cx - r, cy + r)

                el = BlockGeomCircleItem(tl.x(), tl.y(), r * 2.0, r * 2.0)
                pen = QPen(entity_stroke_qcolor(doc, entity), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, entity_effective_linetype(doc, entity))
                el.setPen(pen)
                self._tag_movable_geom_circle(el, handle)
                el.setZValue(0)
                self.addItem(el)
            elif et == "LWPOLYLINE":
                if not get_uid(entity) and should_add_passive_primitive(entity):
                    add_passive_layout_primitive_items(doc, self, entity)
                    continue
                rows = list(entity.get_points("xyb"))
                if len(rows) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(_dxf_to_scene_pt(float(rows[0][0]), float(rows[0][1])))
                for i in range(len(rows) - 1):
                    x0, y0 = float(rows[i][0]), float(rows[i][1])
                    b0 = float(rows[i][2]) if len(rows[i]) > 2 else 0.0
                    x1, y1 = float(rows[i + 1][0]), float(rows[i + 1][1])
                    if abs(b0) < 1e-12:
                        p = _dxf_to_scene_pt(x1, y1)
                        path.lineTo(p.x(), p.y())
                    else:
                        append_bulge_arc_to_path(path, x0, y0, x1, y1, b0)
                if bool(entity.closed):
                    path.closeSubpath()
                rows_xyb: list[tuple[float, float, float]] = [
                    (
                        float(rows[i][0]),
                        float(rows[i][1]),
                        float(rows[i][2]) if len(rows[i]) > 2 else 0.0,
                    )
                    for i in range(len(rows))
                ]
                pip = BlockGeomLwPolyItem(
                    path,
                    rows_xyb=rows_xyb,
                    closed=bool(entity.closed),
                )
                pen = QPen(entity_stroke_qcolor(doc, entity), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, entity_effective_linetype(doc, entity))
                pip.setPen(pen)
                pip.setBrush(Qt.BrushStyle.NoBrush)
                self._tag_movable_geom_lwpoly(pip, handle)
                pip.setZValue(0)
                self.addItem(pip)
            elif et == "ARC":
                uid_a = get_uid(entity)
                if uid_a and get_type(entity) == ENTITY_TYPE_USER_ARC:
                    c = entity.dxf.center
                    cx, cy = float(c.x), float(c.y)
                    r = float(entity.dxf.radius)
                    sa = float(entity.dxf.start_angle)
                    ea = float(entity.dxf.end_angle)
                    lt = user_sketch_display_linetype_for_entity(entity)
                    st = entity_stroke_qcolor(doc, entity)
                    ua = UserArcItem(uid_a, cx, cy, r, sa, ea, linetype=lt, stroke_color=st)
                    ua.setZValue(40)
                    self.addItem(ua)
                    continue
                if not uid_a and should_add_passive_primitive(entity):
                    add_passive_layout_primitive_items(doc, self, entity)
                    continue
                c = entity.dxf.center
                arc = ConstructionArc(
                    center=(float(c.x), float(c.y)),
                    radius=float(entity.dxf.radius),
                    start_angle=float(entity.dxf.start_angle),
                    end_angle=float(entity.dxf.end_angle),
                )
                pts = list(arc.flattening(_ARC_FLATTEN_MM))
                if len(pts) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(_dxf_to_scene_pt(float(pts[0].x), float(pts[0].y)))
                for p in pts[1:]:
                    pp = _dxf_to_scene_pt(float(p.x), float(p.y))
                    path.lineTo(pp.x(), pp.y())
                pip = QGraphicsPathItem(path)
                pen = QPen(entity_stroke_qcolor(doc, entity), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, entity_effective_linetype(doc, entity))
                pip.setPen(pen)
                pip.setBrush(Qt.BrushStyle.NoBrush)
                self._tag_geom_arc_item(pip, handle)
                pip.setZValue(0)
                self.addItem(pip)
            elif et == "POINT" and parse_port_layer(str(entity.dxf.layer)) is not None:
                ix, iy = float(entity.dxf.location.x), float(entity.dxf.location.y)
                marker = PortMarkerItem(-0.35, -0.35, 0.7, 0.7)
                marker.place_at_dxf_mm(ix, iy)
                pen = QPen(QColor(140, 230, 150))
                pen.setCosmetic(True)
                pen.setWidth(2)
                marker.setPen(pen)
                marker.setBrush(QColor(140, 230, 150, 45))
                marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
                marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                marker.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
                marker.setData(0, handle)
                marker.setData(1, ITEM_KIND_PORT)
                marker.setZValue(50)
                self.addItem(marker)
            elif et == "ATTDEF":
                if not handle:
                    continue
                ad = AttdefEditItem(
                    self._get_session,
                    handle,
                    snap_pitch_mm=lambda: float(self.snap_pitch_mm),
                )
                self.addItem(ad)
                ad.sync_pos_from_entity()
            elif et == "TEXT" and handle:
                tx = BlockTextEditItem(
                    self._get_session,
                    handle,
                    snap_pitch_mm=lambda: float(self.snap_pitch_mm),
                )
                self.addItem(tx)
                tx.sync_pos_from_entity()
            elif et == "MTEXT" and handle:
                mt = BlockMTextEditItem(
                    self._get_session,
                    handle,
                    lambda: float(self.snap_pitch_mm),
                    entity,
                )
                self.addItem(mt)
                mt.sync_pos_from_entity()
        self.set_placement_tool(self._placement)
        pad = 10.0
        half = float(BLOCK_EDIT_MIN_SCENE_HALF_MM)
        min_r = QRectF(-half, -half, 2 * half, 2 * half)
        br = self.itemsBoundingRect()
        if br.isValid():
            self.setSceneRect(br.adjusted(-pad, -pad, pad, pad).united(min_r))
        else:
            self.setSceneRect(min_r.adjusted(-pad, -pad, pad, pad))

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self._user_line_endpoint_drag is not None:
            li, end_i = self._user_line_endpoint_drag
            ms = event.modifiers() | QApplication.keyboardModifiers()
            shift = bool(ms & Qt.KeyboardModifier.ShiftModifier)
            li.set_dragged_endpoint_scene(end_i, event.scenePos(), shift=shift)
            event.accept()
            return
        super().mouseMoveEvent(event)
        sp = event.scenePos()
        if self._placement == "port":
            self._ensure_port_hover(sp)
        elif self._placement == "line" and self._line_p0_dxf is not None:
            self._update_line_preview(sp, event.modifiers())
        elif self._placement == "circle" and self._circle_c_dxf is not None:
            self._update_circle_preview(sp)
        elif (
            self._placement == "arc"
            and len(self._sketch_arc_dxf_pts) == 1
            and self._sketch_preview_arc_chord is not None
        ):
            self._update_arc_chord_rubber(sp)
        elif (
            self._placement == "arc"
            and len(self._sketch_arc_dxf_pts) == 2
            and self._sketch_preview_arc is not None
        ):
            self._update_arc_preview(sp)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._placement in ("line", "circle", "arc"):
            if self._placement == "line":
                self._reset_line_draft()
                self.status_message.emit("線分: 1点目からやり直します。")
            elif self._placement == "circle":
                self._reset_circle_draft()
                self.status_message.emit("円: 中心からやり直します。")
            else:
                self._reset_arc_draft()
                self.status_message.emit("円弧: 1点目からやり直します。")
            event.accept()
            return

        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._placement is None
            and self._user_line_endpoint_drag is None
        ):
            sp = event.scenePos()
            sels = self.selectedItems()
            if len(sels) == 1 and isinstance(sels[0], UserLineItem):
                li2 = sels[0]
                end_i = li2.hit_endpoint_index(sp)
                if end_i is not None:
                    self._user_line_endpoint_drag = (li2, end_i)
                    event.accept()
                    return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "line":
            session = self._get_session()
            blk = None if session is None else session.scratch_block()
            if session is None or blk is None:
                super().mousePressEvent(event)
                return
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if self._line_p0_dxf is None:
                x, y = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
                self._line_p0_dxf = (x, y)
                ln = QGraphicsLineItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, self._sketch_line_linetype())
                ln.setPen(pen)
                ln.setZValue(_PREVIEW_Z)
                _mark_preview_item(ln)
                self.addItem(ln)
                self._sketch_preview_line = ln
                self._update_line_preview(event.scenePos(), event.modifiers())
                self.status_message.emit(
                    "直線: 2点目をクリックで確定（Shiftで水平・垂直）。右クリックでキャンセル。"
                )
                event.accept()
                return
            anchor = self._line_p0_dxf
            x, y = user_line_end_dxf_from_scene(anchor, event.scenePos(), shift, pitch=self.snap_pitch_mm)
            x, y = snap_dxf_pos(x, y, pitch=self.snap_pitch_mm)
            x0, y0 = anchor
            if abs(x - x0) < 1e-9 and abs(y - y0) < 1e-9:
                event.accept()
                return
            lt = self._sketch_line_linetype()
            with session.begin("block_edit_add_user_line"):
                add_user_line_to_block(blk, anchor, (x, y), lt)
            self._reset_line_draft()
            self.refresh_from_session()
            self.edited.emit()
            self.status_message.emit("USER_LINE を追加しました（レイヤ LD_SYMBOL）。")
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "circle":
            session = self._get_session()
            blk = None if session is None else session.scratch_block()
            if session is None or blk is None:
                super().mousePressEvent(event)
                return
            if self._circle_c_dxf is None:
                x, y = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
                self._circle_c_dxf = (x, y)
                el = QGraphicsEllipseItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                el.setPen(pen)
                el.setBrush(Qt.BrushStyle.NoBrush)
                el.setZValue(_PREVIEW_Z)
                _mark_preview_item(el)
                self.addItem(el)
                self._sketch_preview_circle = el
                self._update_circle_preview(event.scenePos())
                self.status_message.emit("円: もう一度クリックで半径確定。右クリックでキャンセル。")
                event.accept()
                return
            r = self._circle_radius_mm(self._circle_c_dxf, event.scenePos())
            if r < self.snap_pitch_mm * 0.5:
                event.accept()
                return
            lt = self._sketch_line_linetype()
            with session.begin("block_edit_add_user_circle"):
                add_user_circle_to_block(blk, self._circle_c_dxf, r, lt)
            self._reset_circle_draft()
            self.refresh_from_session()
            self.edited.emit()
            self.status_message.emit("USER_CIRCLE を追加しました（レイヤ LD_SYMBOL）。")
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "arc":
            session = self._get_session()
            blk = None if session is None else session.scratch_block()
            if session is None or blk is None:
                super().mousePressEvent(event)
                return
            xd, yd = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
            if len(self._sketch_arc_dxf_pts) == 0:
                self._sketch_arc_dxf_pts.append((xd, yd))
                chord = QGraphicsLineItem()
                pen_ch = QPen(QColor(180, 220, 255), 0)
                pen_ch.setStyle(Qt.PenStyle.DashLine)
                pen_ch.setCosmetic(True)
                chord.setPen(pen_ch)
                chord.setZValue(_PREVIEW_Z)
                _mark_preview_item(chord)
                self.addItem(chord)
                self._sketch_preview_arc_chord = chord
                self._update_arc_chord_rubber(event.scenePos())
                self.status_message.emit(
                    "円弧: 2点目（弧上の点）をクリック。"
                    " 移動中は1点目からの破線で案内します。右クリックでキャンセル。"
                )
                event.accept()
                return
            if len(self._sketch_arc_dxf_pts) == 1:
                p0 = self._sketch_arc_dxf_pts[0]
                if same_dxf_point(p0, (xd, yd)):
                    event.accept()
                    return
                self._sketch_arc_dxf_pts.append((xd, yd))
                if self._sketch_preview_arc_chord is not None:
                    self.removeItem(self._sketch_preview_arc_chord)
                    self._sketch_preview_arc_chord = None
                self._add_arc_locked_vertex_markers()
                pip = QGraphicsPathItem()
                pen = QPen(QColor(180, 220, 255), 0)
                pen.setCosmetic(True)
                apply_dxf_linetype_to_pen(pen, self._sketch_line_linetype())
                pip.setPen(pen)
                pip.setBrush(Qt.BrushStyle.NoBrush)
                pip.setZValue(_PREVIEW_Z)
                _mark_preview_item(pip)
                self.addItem(pip)
                self._sketch_preview_arc = pip
                self._update_arc_preview(event.scenePos())
                self.status_message.emit("円弧: 終了点をクリックで確定。右クリックでやり直し。")
                event.accept()
                return
            if len(self._sketch_arc_dxf_pts) == 2:
                p0, p1 = self._sketch_arc_dxf_pts[0], self._sketch_arc_dxf_pts[1]
                if same_dxf_point(p0, (xd, yd)) or same_dxf_point(p1, (xd, yd)):
                    event.accept()
                    return
                geom = try_dxf_arc_through_three_points(p0, p1, (xd, yd))
                if geom is None:
                    event.accept()
                    return
                (cx, cy), r, sa, ea = geom
                lt = self._sketch_line_linetype()
                with session.begin("block_edit_add_user_arc"):
                    add_user_arc_to_block(blk, (cx, cy), r, sa, ea, lt)
                self._reset_arc_draft()
                self.refresh_from_session()
                self.edited.emit()
                self.status_message.emit("USER_ARC を追加しました（レイヤ LD_SYMBOL）。")
                event.accept()
                return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "attdef":
            session = self._get_session()
            blk = None if session is None else session.scratch_block()
            if session is None or blk is None:
                super().mousePressEvent(event)
                return
            par = QApplication.activeWindow()
            bn = session.scratch_definition_name()
            pair = _prompt_new_block_attdef(par, blk, block_name=bn)
            if pair is None:
                event.accept()
                return
            tag, text = pair
            x, y = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
            try:
                with session.begin("block_edit_add_attdef"):
                    add_attdef_to_block(blk, tag, (x, y), str(text))
            except ValueError as ex:
                QMessageBox.warning(
                    par,
                    "ATTDEF を配置",
                    str(ex) or "タグが重複しているか配置できません。",
                )
                event.accept()
                return
            self.refresh_from_session()
            self.clearSelection()
            self.edited.emit()
            self.status_message.emit(f"ATTDEF {str(tag).strip()!r} を配置しました（LD_TEXT）。")
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "dxf_text":
            session = self._get_session()
            blk = None if session is None else session.scratch_block()
            if session is None or blk is None:
                super().mousePressEvent(event)
                return
            par = QApplication.activeWindow()
            prompted = prompt_dxf_text_string_and_height(
                par,
                window_title="TEXT を配置",
                empty_text_warning_title="TEXT を配置",
                default_height_mm=float(USER_TEXT_DEFAULT_HEIGHT_MM),
            )
            if prompted is None:
                event.accept()
                return
            s, h_mm = prompted
            x, y = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
            with session.begin("block_edit_add_plain_text"):
                add_plain_text_to_block(blk, (x, y), s, height_mm=h_mm)
            self.refresh_from_session()
            self.clearSelection()
            self.edited.emit()
            self.status_message.emit("TEXT を配置しました（LD_TEXT）。")
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and self._placement == "port":
            session = self._get_session()
            if session is None:
                super().mousePressEvent(event)
                return
            layer = self._request_port_layer()
            if not layer:
                event.accept()
                return
            blk = session.scratch_block()
            if blk is None:
                super().mousePressEvent(event)
                return
            if port_layer_is_taken(blk, layer):
                self.status_message.emit(PORT_LAYER_TAKEN_MESSAGE)
                event.accept()
                return
            x, y = snap_dxf_pos(*dxf_from_scene_pos(event.scenePos()), pitch=self.snap_pitch_mm)
            with session.begin("block_edit_add_port"):
                blk.add_point((x, y), dxfattribs={"layer": layer})
            self.refresh_from_session()
            self.edited.emit()
            event.accept()
            return

        super().mousePressEvent(event)
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._placement is None
            and self._user_line_endpoint_drag is None
        ):
            self._snapshot_selection_drag_starts()

    def _entity_in_block(self, blk, handle: str):
        for e in blk:
            if str(getattr(e.dxf, "handle", "") or "") == handle:
                return e
        return None

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._user_line_endpoint_drag is not None:
            self._user_line_endpoint_drag = None
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        try:
            # Run every commit path; ``a or b or ...`` would skip ports/ATTDEF after geom.
            edited = any(
                (
                    self._commit_geom_block_moves(),
                    self._commit_port_moves(),
                    self._commit_user_line_moves(),
                    self._commit_user_circle_moves(),
                    self._commit_user_arc_moves(),
                    self._commit_attdef_moves(),
                    self._commit_block_text_entity_moves(),
                )
            )
            if edited:
                self.refresh_from_session()
                self.edited.emit()
        finally:
            self._drag_start_scene = None

    def _scene_delta_to_dxf_mm(self, delta_scene: QPointF) -> tuple[float, float]:
        return float(delta_scene.x()), float(-delta_scene.y())

    def _snapshot_selection_drag_starts(self) -> None:
        self._drag_start_scene = {}
        for it in self.selectedItems():
            if it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
                self._drag_start_scene[id(it)] = QPointF(it.scenePos())

    def _group_drag_delta_scene(self) -> QPointF | None:
        if not self._drag_start_scene:
            return None
        for it in self.selectedItems():
            iid = id(it)
            if iid not in self._drag_start_scene:
                continue
            if not (it.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable):
                continue
            p0 = self._drag_start_scene[iid]
            d = it.scenePos() - p0
            if abs(d.x()) > 1e-9 or abs(d.y()) > 1e-9:
                return d
        return None

    def _item_scene_dragged_since_press(self, item: QGraphicsItem) -> bool:
        """Whether this item was under snap-drag tracking and moved beyond jitter since mouse press.

        ATTDEF/port DXF commits use Qt ItemChange ``*_moved`` flags; those can spike without a real
        drag when another entity moves or rubber-band interaction ends. Require correlation with the
        per-item positions captured in :attr:`_drag_start_scene` at left-button press.

        Args:
            item: Candidate port marker or ATTDEF item.

        Returns:
            True when ``item`` appears in the snapshot and its scene position moved from
            that snapshot by more than jitter tolerance.
        """
        ds = self._drag_start_scene
        if not ds:
            return False
        iid = id(item)
        if iid not in ds:
            return False
        return (
            item.scenePos() - ds[iid]
        ).manhattanLength() > _BLOCK_EDIT_DRAG_COMMIT_EPS_SCENE_MM

    def _commit_geom_block_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        blk = session.scratch_block()
        if blk is None:
            return False
        geom_edited = False
        for item in list(self.items()):
            if str(item.data(1) or "") != ITEM_KIND_GEOM:
                continue
            handle = str(item.data(0) or "")
            if not handle:
                continue
            ent = self._entity_in_block(blk, handle)
            if ent is None:
                continue
            if isinstance(item, BlockGeomLineItem):
                if not getattr(item, "_geom_moved", False):
                    continue
                if ent.dxftype() != "LINE":
                    continue
                p1s = item.mapToScene(item.line().p1())
                p2s = item.mapToScene(item.line().p2())
                x0, y0 = snap_dxf_pos(*dxf_from_scene_pos(p1s), pitch=self.snap_pitch_mm)
                x1, y1 = snap_dxf_pos(*dxf_from_scene_pos(p2s), pitch=self.snap_pitch_mm)
                with session.begin("block_edit_move_geom_line"):
                    ent.dxf.start = (x0, y0, 0.0)
                    ent.dxf.end = (x1, y1, 0.0)
                item._geom_moved = False
                geom_edited = True
            elif isinstance(item, BlockGeomCircleItem):
                if not getattr(item, "_geom_moved", False):
                    continue
                if ent.dxftype() != "CIRCLE":
                    continue
                ctr = item.mapToScene(item.rect().center())
                cx, cy = snap_dxf_pos(*dxf_from_scene_pos(ctr), pitch=self.snap_pitch_mm)
                r_mm = float(max(item.rect().width(), item.rect().height())) * 0.5
                r_mm = max(1e-9, r_mm)
                with session.begin("block_edit_move_geom_circle"):
                    ent.dxf.center = (cx, cy, 0.0)
                    ent.dxf.radius = r_mm
                item._geom_moved = False
                geom_edited = True
            elif isinstance(item, BlockGeomLwPolyItem):
                if not getattr(item, "_geom_moved", False):
                    continue
                if ent.dxftype() != "LWPOLYLINE":
                    continue
                dx, dy = dxf_from_scene_pos(item.pos())
                dx, dy = snap_dxf_pos(dx, dy, pitch=self.snap_pitch_mm)
                base = item._ld_rows_xyb
                new_rows = [(float(x) + dx, float(y) + dy, float(b)) for x, y, b in base]
                with session.begin("block_edit_move_geom_lwpoly"):
                    ent.set_points(new_rows, format="xyb")
                    ent.closed = item._ld_closed
                item._geom_moved = False
                geom_edited = True
        return geom_edited

    def _commit_port_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        blk = session.scratch_block()
        if blk is None:
            return False
        delta_scene = self._group_drag_delta_scene()
        ds = self._drag_start_scene
        moves: list[tuple[object, float, float]] = []
        for item in self.items():
            if str(item.data(1) or "") != ITEM_KIND_PORT:
                continue
            handle = str(item.data(0) or "")
            if not handle:
                continue
            ent = None
            for e in blk:
                if str(getattr(e.dxf, "handle", "") or "") == handle:
                    ent = e
                    break
            if ent is None:
                continue
            # Match geom sketch commits: only items the user actually dragged.
            if not getattr(item, "_pm_moved", False):
                continue
            if not self._item_scene_dragged_since_press(item):
                item._pm_moved = False
                continue
            xd, yd = snap_dxf_pos(*dxf_from_scene_pos(item.scenePos()), pitch=self.snap_pitch_mm)
            ox, oy = float(ent.dxf.location.x), float(ent.dxf.location.y)
            if abs(xd - ox) < 1e-9 and abs(yd - oy) < 1e-9:
                if (
                    delta_scene is not None
                    and ds is not None
                    and item.isSelected()
                    and id(item) in ds
                    and (item.scenePos() - ds[id(item)]).manhattanLength() <= 1e-6
                ):
                    dx_mm, dy_mm = self._scene_delta_to_dxf_mm(delta_scene)
                    xd, yd = snap_dxf_pos(ox + dx_mm, oy + dy_mm, pitch=self.snap_pitch_mm)
            if abs(xd - ox) < 1e-9 and abs(yd - oy) < 1e-9:
                continue
            moves.append((ent, xd, yd))
        if moves:
            with session.begin("block_edit_move_port"):
                for ent, xd, yd in moves:
                    ent.dxf.location = (xd, yd, 0.0)
        for item in self.items():
            if isinstance(item, PortMarkerItem):
                item._pm_moved = False
        return bool(moves)

    def _commit_user_line_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        doc = session.scratch_doc
        moved = False
        for item in self.items():
            if not isinstance(item, UserLineItem):
                continue
            if not getattr(item, "_moved", False):
                continue
            (x0, y0), (x1, y1) = item.line_endpoints_dxf()
            x0, y0 = snap_dxf_pos(x0, y0, pitch=self.snap_pitch_mm)
            x1, y1 = snap_dxf_pos(x1, y1, pitch=self.snap_pitch_mm)
            with session.begin("block_edit_move_user_line"):
                update_scratch_user_line_geometry(doc, item.sketch_uid, (x0, y0), (x1, y1))
            item._moved = False
            moved = True
        return moved

    def _commit_user_circle_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        doc = session.scratch_doc
        moved = False
        for item in self.items():
            if not isinstance(item, UserCircleItem):
                continue
            if not getattr(item, "_moved", False):
                continue
            (cx, cy), r = item.center_radius_dxf()
            cx, cy = snap_dxf_pos(cx, cy, pitch=self.snap_pitch_mm)
            with session.begin("block_edit_move_user_circle"):
                update_scratch_user_circle_geometry(doc, item.sketch_uid, (cx, cy), r)
            item._moved = False
            moved = True
        return moved

    def _commit_user_arc_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        doc = session.scratch_doc
        sp = float(self.snap_pitch_mm)
        moved = False
        for item in self.items():
            if not isinstance(item, UserArcItem):
                continue
            if not getattr(item, "_moved", False):
                continue
            (cx, cy), r, sa, ea = item.arc_geometry_dxf()
            cx, cy = snap_dxf_pos(cx, cy, pitch=sp)
            r = max(sp, round(r / sp) * sp)
            with session.begin("block_edit_move_user_arc"):
                update_scratch_user_arc_geometry(doc, item.sketch_uid, (cx, cy), r, sa, ea)
            item._moved = False
            moved = True
        return moved

    def _commit_attdef_moves(self) -> bool:
        session = self._get_session()
        if session is None:
            return False
        blk = session.scratch_block()
        if blk is None:
            return False
        delta_scene = self._group_drag_delta_scene()
        ds = self._drag_start_scene
        moves: list[tuple[object, float, float]] = []
        for item in self.items():
            if not isinstance(item, AttdefEditItem):
                continue
            handle = str(item.data(0) or "")
            if not handle:
                continue
            ent = None
            for e in blk:
                if str(getattr(e.dxf, "handle", "") or "") == handle:
                    ent = e
                    break
            if ent is None or ent.dxftype() != "ATTDEF":
                continue
            # Avoid rewriting DXF when snap pitch rounds scene vs stored insert without a drag.
            if not getattr(item, "_moved", False):
                continue
            if not self._item_scene_dragged_since_press(item):
                item._moved = False
                continue
            ix, iy = snap_dxf_pos(*dxf_from_scene_pos(item.scenePos()), pitch=self.snap_pitch_mm)
            ox, oy = float(ent.dxf.insert.x), float(ent.dxf.insert.y)
            if abs(ix - ox) < 1e-9 and abs(iy - oy) < 1e-9:
                if (
                    delta_scene is not None
                    and ds is not None
                    and item.isSelected()
                    and id(item) in ds
                    and (item.scenePos() - ds[id(item)]).manhattanLength() <= 1e-6
                ):
                    dx_mm, dy_mm = self._scene_delta_to_dxf_mm(delta_scene)
                    ix, iy = snap_dxf_pos(ox + dx_mm, oy + dy_mm, pitch=self.snap_pitch_mm)
            item._moved = False
            if abs(ix - ox) < 1e-9 and abs(iy - oy) < 1e-9:
                continue
            moves.append((ent, ix, iy))
        if not moves:
            return False
        with session.begin("block_edit_move_attdef"):
            for ent, ix, iy in moves:
                ent.dxf.insert = (ix, iy, 0.0)
                ent.dxf.align_point = (ix, iy, 0.0)
        return True

    def _commit_block_text_entity_moves(self) -> bool:
        """Persist drag for ``TEXT`` / ``MTEXT`` placement (insert; ``TEXT`` also updates align)."""

        session = self._get_session()
        if session is None:
            return False
        blk = session.scratch_block()
        if blk is None:
            return False
        delta_scene = self._group_drag_delta_scene()
        ds = self._drag_start_scene
        moves_text: list[tuple[object, float, float]] = []
        moves_mtext: list[tuple[object, float, float]] = []
        for item in self.items():
            if not isinstance(item, (BlockTextEditItem, BlockMTextEditItem)):
                continue
            handle = str(item.data(0) or "")
            if not handle:
                continue
            ent = self._entity_in_block(blk, handle)
            if ent is None:
                continue
            dt = ent.dxftype()
            if isinstance(item, BlockTextEditItem) and dt != "TEXT":
                continue
            if isinstance(item, BlockMTextEditItem) and dt != "MTEXT":
                continue
            if not getattr(item, "_moved", False):
                continue
            if not self._item_scene_dragged_since_press(item):
                item._moved = False
                continue
            ix, iy = snap_dxf_pos(*dxf_from_scene_pos(item.scenePos()), pitch=self.snap_pitch_mm)
            ox, oy = float(ent.dxf.insert.x), float(ent.dxf.insert.y)
            if abs(ix - ox) < 1e-9 and abs(iy - oy) < 1e-9:
                if (
                    delta_scene is not None
                    and ds is not None
                    and item.isSelected()
                    and id(item) in ds
                    and (item.scenePos() - ds[id(item)]).manhattanLength() <= 1e-6
                ):
                    dx_mm, dy_mm = self._scene_delta_to_dxf_mm(delta_scene)
                    ix, iy = snap_dxf_pos(ox + dx_mm, oy + dy_mm, pitch=self.snap_pitch_mm)
            item._moved = False
            if abs(ix - ox) < 1e-9 and abs(iy - oy) < 1e-9:
                continue
            if dt == "TEXT":
                moves_text.append((ent, ix, iy))
            else:
                moves_mtext.append((ent, ix, iy))
        if not moves_text and not moves_mtext:
            return False
        with session.begin("block_edit_move_plain_text"):
            for ent, ix, iy in moves_text:
                ent.dxf.insert = (ix, iy, 0.0)
                ent.dxf.align_point = (ix, iy, 0.0)
            for ent, ix, iy in moves_mtext:
                ent.dxf.insert = (ix, iy, 0.0)
        return True

    def delete_selected_ports(self) -> None:
        self.delete_selected_editor_items()

    def delete_selected_editor_items(self) -> None:
        session = self._get_session()
        if session is None:
            return
        blk = session.scratch_block()
        if blk is None:
            return

        port_handles = [
            str(it.data(0) or "")
            for it in self.selectedItems()
            if str(it.data(1) or "") == ITEM_KIND_PORT and str(it.data(0) or "")
        ]
        attdef_handles = [
            str(it.data(0) or "")
            for it in self.selectedItems()
            if str(it.data(1) or "") == ITEM_KIND_ATTDEF and str(it.data(0) or "")
        ]
        geom_handles = [
            str(it.data(0) or "")
            for it in self.selectedItems()
            if str(it.data(1) or "") == ITEM_KIND_GEOM and str(it.data(0) or "")
        ]
        block_text_handles = [
            str(it.data(0) or "")
            for it in self.selectedItems()
            if str(it.data(1) or "") in (ITEM_KIND_BLOCK_TEXT, ITEM_KIND_BLOCK_MTEXT)
            and str(it.data(0) or "")
        ]
        uids = [
            it.sketch_uid
            for it in self.selectedItems()
            if isinstance(it, UserLineItem | UserCircleItem | UserArcItem)
        ]

        if not port_handles and not geom_handles and not uids and not attdef_handles and not block_text_handles:
            return

        to_delete: list[object] = []
        for e in list(blk):
            h = str(getattr(e.dxf, "handle", "") or "")
            if h in port_handles or h in geom_handles or h in attdef_handles or h in block_text_handles:
                to_delete.append(e)
        for uid in uids:
            ent = find_entity_by_uid(session.scratch_doc, uid)
            if ent is not None:
                to_delete.append(ent)
        seen: set[str] = set()
        uniq_del: list[object] = []
        for e in to_delete:
            eh = str(getattr(e.dxf, "handle", "") or "")
            if eh and eh not in seen:
                seen.add(eh)
                uniq_del.append(e)
        with session.begin("block_edit_delete_entities"):
            for e in uniq_del:
                blk.delete_entity(e)
        self.refresh_from_session()
        self.edited.emit()
