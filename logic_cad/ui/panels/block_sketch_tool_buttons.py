"""Block-edit palette: annotation sketch icons (subset of main window tools)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton, QWidget

from logic_cad.ui.sketch_tool_icons import (
    sketch_arc_icon,
    sketch_attdef_icon,
    sketch_circle_icon,
    sketch_line_icon,
    sketch_text_icon,
)

_SK_ICO = QSize(24, 24)


@dataclass(frozen=True)
class BlockAnnotationSketchButtons:
    """Checkable sketch tools for block definition (line / circle / arc / ATTDEF / TEXT)."""

    line: QPushButton
    circle: QPushButton
    arc: QPushButton
    text: QPushButton
    plain_text: QPushButton


def create_block_annotation_sketch_buttons(parent: QWidget | None = None) -> BlockAnnotationSketchButtons:
    """Create checkable sketch buttons; caller wires exclusivity / placement mode."""

    btn_line = QPushButton(parent)
    btn_line.setCheckable(True)
    btn_line.setAutoDefault(False)
    btn_line.setDefault(False)
    btn_line.setObjectName("blockSketchToolLine")
    btn_line.setIcon(sketch_line_icon())
    btn_line.setIconSize(_SK_ICO)
    btn_line.setToolTip(
        "直線（USER_LINE）: 2点で描画。グリッドにスナップ。Shiftで水平/垂直。レイヤは LD_SYMBOL。"
        " 配置ツール中はクリックが配置優先（下に図形があっても同じ）。右クリックで1点目キャンセル。"
    )
    btn_line.setAccessibleName("直線")

    btn_circle = QPushButton(parent)
    btn_circle.setCheckable(True)
    btn_circle.setAutoDefault(False)
    btn_circle.setDefault(False)
    btn_circle.setObjectName("blockSketchToolCircle")
    btn_circle.setIcon(sketch_circle_icon())
    btn_circle.setIconSize(_SK_ICO)
    btn_circle.setToolTip(
        "円（USER_CIRCLE）: 1点目で中心、2点目で半径。グリッドスナップ。レイヤ LD_SYMBOL。"
        " 配置ツール中はクリックが配置優先。右クリックでキャンセル。"
    )
    btn_circle.setAccessibleName("円")

    btn_arc = QPushButton(parent)
    btn_arc.setCheckable(True)
    btn_arc.setAutoDefault(False)
    btn_arc.setDefault(False)
    btn_arc.setObjectName("blockSketchToolArc")
    btn_arc.setIcon(sketch_arc_icon())
    btn_arc.setIconSize(_SK_ICO)
    btn_arc.setToolTip(
        "円弧（USER_ARC）: 開始→弧上→終了の3点。グリッドスナップ。レイヤ LD_SYMBOL。"
        " 1→2点は破線、2点目以降は弧プレビュー。右クリックでやり直し。"
    )
    btn_arc.setAccessibleName("円弧")

    btn_text = QPushButton(parent)
    btn_text.setCheckable(True)
    btn_text.setAutoDefault(False)
    btn_text.setDefault(False)
    btn_text.setObjectName("blockSketchToolAttdef")
    btn_text.setIcon(sketch_attdef_icon())
    btn_text.setIconSize(_SK_ICO)
    btn_text.setToolTip(
        "属性定義（ATTDEF）: クリックし、タグ名と既定文字列を入力。レイヤ LD_TEXT。シンボル表示用（SYM, LABEL0 など）。"
        " 配置ツール中はクリックが配置優先。"
    )
    btn_text.setAccessibleName("ATTDEF")

    btn_plain = QPushButton(parent)
    btn_plain.setCheckable(True)
    btn_plain.setAutoDefault(False)
    btn_plain.setDefault(False)
    btn_plain.setObjectName("blockSketchToolPlainText")
    btn_plain.setIcon(sketch_text_icon())
    btn_plain.setIconSize(_SK_ICO)
    btn_plain.setToolTip(
        "1行テキスト（TEXT）: クリック位置に配置。レイヤ LD_TEXT。"
        " ブロック内の注釈やラベル用（ATTDEF/SYM とは別エンティティ）。配置ツール中はクリックが配置優先。"
    )
    btn_plain.setAccessibleName("TEXT")

    return BlockAnnotationSketchButtons(
        line=btn_line,
        circle=btn_circle,
        arc=btn_arc,
        text=btn_text,
        plain_text=btn_plain,
    )
