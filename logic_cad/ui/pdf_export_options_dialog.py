"""Modal dialog for PDF export settings before choosing output path."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from logic_cad.core.services.pdf_export_service import PdfExportOptions
from logic_cad.ui.layer_lineweight_dialog import LayerLineweightDialog

if TYPE_CHECKING:
    from logic_cad.core.logic_diagram import LogicDiagram


class PdfExportOptionsDialog(QDialog):
    """PDF 保存ダイアログの前に白黒出力や関連プロジェクト設定を開けるモーダル。"""

    def __init__(self, diagram: LogicDiagram, parent=None) -> None:
        super().__init__(parent)
        self._diagram = diagram
        self.setWindowTitle("PDF 書き出し設定")
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog { background-color: #2a2c30; color: #d8d8dc; }
            QLabel { color: #d8d8dc; }
            QCheckBox { color: #e8e8ec; }
            QPushButton {
                background-color: #4a4f59; color: #ffffff; padding: 4px 12px;
                border: none; border-radius: 2px;
            }
            QPushButton:hover { background-color: #5a6070; }
            QDialogButtonBox QPushButton {
                background-color: #3d6fb8; color: #ffffff; padding: 4px 12px;
                border: none; border-radius: 2px;
            }
            QDialogButtonBox QPushButton:hover { background-color: #4a7ec8; }
            """
        )

        self._mono = QCheckBox("白黒で出力（前景を黒・背景を白）")
        self._mono.setChecked(True)
        self._drawing_props = QPushButton("図面プロパティ…")
        self._drawing_props.clicked.connect(self._open_drawing_properties)
        self._preferred_font = QPushButton("優先フォント…")
        self._preferred_font.clicked.connect(self._open_preferred_font_settings)
        self._edit_lineweight = QPushButton("レイヤ線を設定…")
        self._edit_lineweight.clicked.connect(self._open_layer_lineweight_dialog)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("保存先を選ぶ前に出力オプションを指定します。"))
        layout.addWidget(self._mono)
        layout.addWidget(self._drawing_props)
        layout.addWidget(self._preferred_font)
        layout.addWidget(self._edit_lineweight)
        layout.addWidget(buttons)

    def _open_drawing_properties(self) -> None:
        """親が MainWindow のとき、メニューと同じ図面プロパティを開く。"""

        parent = self.parent()
        fn = getattr(parent, "_drawing_properties", None)
        if callable(fn):
            fn()

    def _open_preferred_font_settings(self) -> None:
        """親が MainWindow のとき、メニューと同じ優先フォント設定を開く。"""

        parent = self.parent()
        fn = getattr(parent, "_preferred_font_settings", None)
        if callable(fn):
            fn()

    def _open_layer_lineweight_dialog(self) -> None:
        """Open shared layer line settings (lineweight and layer color)."""
        dlg = LayerLineweightDialog(self._diagram, self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.changed():
            parent = self.parent()
            if parent is not None:
                if hasattr(parent, "_update_window_title"):
                    parent._update_window_title()
                if hasattr(parent, "_refresh_scene"):
                    parent._refresh_scene()

    def options(self) -> PdfExportOptions:
        """ダイアログで選んだ PDF 書き出しオプションを返す。"""

        return PdfExportOptions(monochrome=self._mono.isChecked())
