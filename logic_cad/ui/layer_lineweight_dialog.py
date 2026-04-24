"""Layer lineweight and layer color editor dialog."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ezdxf.colors import aci2rgb
from ezdxf.document import Drawing

from logic_cad.ui.dxf_display_color import (
    apply_aci_to_dxf_layer,
    apply_qcolor_to_dxf_layer,
    dxf_layer_stroke_qcolor,
    normalize_layer_aci,
    qcolor_to_nearest_aci,
)
from logic_cad.ui.layer_lineweight_utils import (
    all_layer_lineweight_codes,
    layer_name_shown_in_layer_settings_dialog,
    lineweight_code_to_label,
    normalize_layer_lineweight_code,
    sorted_layer_names,
)

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram


class _NoWheelSpinBox(QSpinBox):
    """Spin box that ignores the mouse wheel (prevents accidental value changes in tables)."""

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Do not change the value; allow the wheel to reach the parent (e.g. table scroll).

        Args:
            event: Qt wheel event.
        """
        event.ignore()


class _LayerColorSwatchButton(QPushButton):
    """Shows a solid swatch and opens :class:`QColorDialog` on click."""

    def __init__(self, initial: QColor, parent: QWidget | None = None) -> None:
        """Initialize with *initial* stroke color.

        Args:
            initial: Starting RGB color (alpha ignored for DXF storage).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._color = QColor(
            int(initial.red()),
            int(initial.green()),
            int(initial.blue()),
        )
        self.setFixedHeight(26)
        self.setMinimumWidth(80)
        self._apply_swatch()
        self.clicked.connect(self._pick_color)

    def _apply_swatch(self) -> None:
        """Update stylesheet and tooltip from ``self._color``."""
        hex_col = self._color.name(QColor.NameFormat.HexRgb)
        self.setToolTip(hex_col)
        self.setStyleSheet(
            f"background-color: {hex_col}; border: 1px solid #4a4f59; border-radius: 2px;"
        )

    def _pick_color(self) -> None:
        """Open modal color dialog and adopt the result when accepted.

        Uses Qt's non-native dialog so the Windows color picker does not alter
        application-wide palette / color-scheme appearance while browsing colors.
        """
        parent_widget = self.window() if isinstance(self.window(), QWidget) else None
        dialog = QColorDialog(self._color, parent_widget)
        dialog.setWindowTitle("レイヤの色")
        dialog.setCurrentColor(self._color)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dialog.currentColor()
        if picked.isValid():
            self._color = QColor(picked.red(), picked.green(), picked.blue())
            self._apply_swatch()

    def set_color(self, qc: QColor) -> None:
        """Replace the swatch color without opening the dialog.

        Args:
            qc: Opaque RGB color (alpha ignored).
        """
        self._color = QColor(int(qc.red()), int(qc.green()), int(qc.blue()))
        self._apply_swatch()

    def color(self) -> QColor:
        """Return the current RGB (opaque)."""
        return QColor(self._color)


class _LayerColorCell(QWidget):
    """Layer color editor: true color (RGB) or DXF indexed color (ACI 1–255)."""

    _DATA_TRUE = 0
    _DATA_ACI = 1

    def __init__(self, layer: Any, parent: QWidget | None = None) -> None:
        """Build editor widgets from the current *layer* table entry.

        Args:
            layer: ``doc.layers.get(name)`` table entry (ezdxf layer record).
            parent: Parent widget.
        """
        super().__init__(parent)
        self._mode = QComboBox(self)
        self._mode.addItem("RGB", self._DATA_TRUE)
        self._mode.addItem("色番", self._DATA_ACI)

        self._swatch = _LayerColorSwatchButton(dxf_layer_stroke_qcolor(layer), self)
        self._aci_spin = _NoWheelSpinBox(self)
        self._aci_spin.setRange(1, 255)
        self._aci_spin.setFixedHeight(26)

        self._aci_preview = QLabel(self)
        self._aci_preview.setFixedHeight(26)
        self._aci_preview.setMinimumWidth(80)

        aci_row = QWidget(self)
        aci_layout = QHBoxLayout(aci_row)
        aci_layout.setContentsMargins(0, 0, 0, 0)
        aci_layout.setSpacing(6)
        aci_layout.addWidget(self._aci_spin)
        aci_layout.addWidget(self._aci_preview, 1)

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._swatch)
        self._stack.addWidget(aci_row)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self._mode)
        row.addWidget(self._stack, 1)

        tc = getattr(layer.dxf, "true_color", None)
        self._aci_spin.setValue(normalize_layer_aci(int(layer.dxf.color)))
        self._mode.blockSignals(True)
        if tc is not None:
            self._mode.setCurrentIndex(0)
            self._stack.setCurrentIndex(0)
        else:
            self._mode.setCurrentIndex(1)
            self._stack.setCurrentIndex(1)
            self._refresh_aci_display()
        self._mode.blockSignals(False)

        self._mode.currentIndexChanged.connect(self._on_mode_index_changed)
        self._aci_spin.valueChanged.connect(self._on_aci_spin_changed)

    def _refresh_aci_display(self) -> None:
        """Update ACI spin tooltip and palette color preview from the current index."""
        aci = int(self._aci_spin.value())
        rgb = aci2rgb(aci)
        qc = QColor(int(rgb.r), int(rgb.g), int(rgb.b))
        hex_col = qc.name(QColor.NameFormat.HexRgb)
        tip = f"ACI {aci} ・ {hex_col}"
        self._aci_spin.setToolTip(tip)
        self._aci_preview.setToolTip(tip)
        self._aci_preview.setStyleSheet(
            f"background-color: {hex_col}; border: 1px solid #4a4f59; border-radius: 2px;"
        )

    def _on_aci_spin_changed(self, _value: int) -> None:
        """Keep preview and tooltip in sync while the user edits the index."""
        self._refresh_aci_display()

    def _on_mode_index_changed(self, index: int) -> None:
        """When switching true color vs ACI, seed the other control from the current color."""
        if int(self._mode.itemData(index)) == self._DATA_TRUE:
            rgb = aci2rgb(int(self._aci_spin.value()))
            self._swatch.set_color(
                QColor(int(rgb.r), int(rgb.g), int(rgb.b)),
            )
            self._stack.setCurrentIndex(0)
            return
        self._aci_spin.setValue(qcolor_to_nearest_aci(self._swatch.color()))
        self._refresh_aci_display()
        self._stack.setCurrentIndex(1)

    def wants_true_color(self) -> bool:
        """Return True if the user chose RGB / true_color storage."""
        return int(self._mode.currentData()) == self._DATA_TRUE

    def true_color_pick(self) -> QColor:
        """Return the RGB color selected for true_color mode."""
        return self._swatch.color()

    def aci_value(self) -> int:
        """Return the selected ACI (1–255) for indexed mode."""
        return int(self._aci_spin.value())


def _opaque_rgb_equal(a: QColor, b: QColor) -> bool:
    """Return True if *a* and *b* match in RGB (ignore alpha)."""
    return (
        int(a.red()) == int(b.red())
        and int(a.green()) == int(b.green())
        and int(a.blue()) == int(b.blue())
    )


class LayerLineweightTableWidget(QWidget):
    """QTable widget that edits layer lineweights and colors."""

    def __init__(self, doc: Drawing, parent: QWidget | None = None) -> None:
        """Initialize table widget from *doc*.

        Args:
            doc: Target DXF drawing.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._table = QTableWidget(self)
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["レイヤ名", "線太", "色"])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setAlternatingRowColors(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self._table)
        self._populate(doc)

    def _populate(self, doc: Drawing) -> None:
        """Populate rows from layer table.

        Args:
            doc: Source drawing.
        """
        names = sorted_layer_names(
            layer.dxf.name
            for layer in doc.layers
            if layer_name_shown_in_layer_settings_dialog(layer.dxf.name)
        )
        self._table.setRowCount(len(names))
        for row, layer_name in enumerate(names):
            layer = doc.layers.get(layer_name)
            layer_item = QTableWidgetItem(layer_name)
            layer_item.setFlags(layer_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self._table.setItem(row, 0, layer_item)

            combo = QComboBox(self._table)
            for code in all_layer_lineweight_codes():
                combo.addItem(lineweight_code_to_label(code), int(code))
            current = normalize_layer_lineweight_code(int(layer.dxf.lineweight))
            combo.setCurrentIndex(max(0, combo.findData(current)))
            self._table.setCellWidget(row, 1, combo)

            cell = _LayerColorCell(layer, self._table)
            self._table.setCellWidget(row, 2, cell)

    def apply_changes(self, doc: Drawing) -> bool:
        """Apply UI values to *doc*.

        Args:
            doc: Target drawing.

        Returns:
            True if any layer lineweight or layer color changed.
        """
        changed = False
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            lw_widget = self._table.cellWidget(row, 1)
            col_widget = self._table.cellWidget(row, 2)
            if item is None or not isinstance(lw_widget, QComboBox):
                continue
            layer = doc.layers.get(item.text())
            new_code = int(lw_widget.currentData())
            current_code = normalize_layer_lineweight_code(int(layer.dxf.lineweight))
            if new_code != current_code:
                layer.dxf.lineweight = new_code
                changed = True

            if isinstance(col_widget, _LayerColorCell):
                if col_widget.wants_true_color():
                    picked = col_widget.true_color_pick()
                    current_vis = dxf_layer_stroke_qcolor(layer)
                    if not _opaque_rgb_equal(picked, current_vis):
                        apply_qcolor_to_dxf_layer(layer, picked)
                        changed = True
                else:
                    aci = col_widget.aci_value()
                    tc = getattr(layer.dxf, "true_color", None)
                    same_aci = normalize_layer_aci(int(layer.dxf.color)) == aci
                    if (tc is not None) or (not same_aci):
                        apply_aci_to_dxf_layer(layer, aci)
                        changed = True
        return changed


class LayerLineweightDialog(QDialog):
    """Modal editor for DXF layer lineweights and layer colors (true color or ACI)."""

    def __init__(self, diagram: LogicDiagram, parent: QWidget | None = None) -> None:
        """Initialize dialog.

        Args:
            diagram: Current diagram.
            parent: Parent widget.
        """
        super().__init__(parent)
        self._diagram = diagram
        self._changed = False
        self.setWindowTitle("レイヤ線設定")
        self.setModal(True)
        self.setMinimumWidth(720)
        self.setStyleSheet(
            """
            QDialog { background-color: #2a2c30; color: #d8d8dc; }
            QLabel { color: #d8d8dc; }
            QTableWidget { background-color: #25272b; color: #e8e8ec; gridline-color: #3a3d44; }
            QHeaderView::section { background-color: #343740; color: #e8e8ec; padding: 4px; }
            QComboBox {
                background-color: #343740; color: #ffffff; border: 1px solid #4a4f59; padding: 3px 8px;
            }
            QSpinBox {
                background-color: #343740; color: #ffffff; border: 1px solid #4a4f59;
                padding: 3px 8px;
                padding-right: 15px;
            }
            QDialogButtonBox QPushButton {
                background-color: #3d6fb8; color: #ffffff; padding: 4px 12px;
                border: none; border-radius: 2px;
            }
            QDialogButtonBox QPushButton:hover { background-color: #4a7ec8; }
            """
        )

        self._table_widget = LayerLineweightTableWidget(diagram.doc, self)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                "編集対象レイヤの線太と色を設定します（ポート用・補助レイヤは除く）。"
                "「真色」は 24 ビット真色、番号は索引色（ACI 1〜255）として DXF に保存されます。"
            )
        )
        layout.addWidget(self._table_widget)
        layout.addWidget(self._buttons)

    def _on_accept(self) -> None:
        """Apply current edits and close."""
        self._changed = self._table_widget.apply_changes(self._diagram.doc)
        if self._changed:
            self._diagram.mark_modified()
        self.accept()

    def changed(self) -> bool:
        """Return whether the latest accept changed any value.

        Returns:
            True when lineweight or layer color values were updated.
        """
        return self._changed
