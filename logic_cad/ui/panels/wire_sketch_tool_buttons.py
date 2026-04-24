"""Wire routing and user-sketch toolbar buttons (QSS objectNames, tooltips, icons)."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QPushButton, QWidget

from logic_cad.ui.sketch_tool_icons import (
    sketch_circle_icon,
    sketch_cloud_icon,
    sketch_line_icon,
    sketch_text_icon,
    wire_auto_icon,
    wire_manual_icon,
)

_WIRE_ICO = QSize(22, 22)
_SK_ICO = QSize(24, 24)


@dataclass(frozen=True)
class WireSketchToolButtons:
    auto_wire: QPushButton
    manual_wire: QPushButton
    sk_line: QPushButton
    sk_circle: QPushButton
    sk_cloud: QPushButton
    sk_text: QPushButton


def create_wire_sketch_tool_buttons(parent: QWidget | None = None) -> WireSketchToolButtons:
    btn_auto = QPushButton("  自動配線", parent)
    btn_auto.setCheckable(True)
    btn_auto.setChecked(False)
    btn_auto.setObjectName("wireToolAuto")
    btn_auto.setIcon(wire_auto_icon())
    btn_auto.setIconSize(_WIRE_ICO)
    btn_auto.setToolTip(
        "オン（橙枠）: ポートを2回クリックで自動ルート。オフ: 選択・移動・ワイヤ編集。"
    )

    btn_manual = QPushButton("  手動配線", parent)
    btn_manual.setCheckable(True)
    btn_manual.setChecked(False)
    btn_manual.setObjectName("wireToolManual")
    btn_manual.setIcon(wire_manual_icon())
    btn_manual.setIconSize(_WIRE_ICO)
    btn_manual.setToolTip(
        "オン（橙枠）: 始点ポート→空き地で折れ点→終点ポート。自動配線と同時指定も可。"
        " AND/OR 入力の一括最適化の対象外（シンボル移動時は通常どおり再配線）。"
    )

    btn_sk_line = QPushButton(parent)
    btn_sk_line.setCheckable(True)
    btn_sk_line.setObjectName("sketchToolLine")
    btn_sk_line.setIcon(sketch_line_icon())
    btn_sk_line.setIconSize(_SK_ICO)
    btn_sk_line.setToolTip(
        "直線ツール: 2点で描画（グリッド）。Shift で水平/垂直に拘束。"
        " 右クリックで次の線種。配置後はプロパティでも変更。"
    )
    btn_sk_line.setAccessibleName("直線")

    btn_sk_circle = QPushButton(parent)
    btn_sk_circle.setCheckable(True)
    btn_sk_circle.setObjectName("sketchToolCircle")
    btn_sk_circle.setIcon(sketch_circle_icon())
    btn_sk_circle.setIconSize(_SK_ICO)
    btn_sk_circle.setToolTip(
        "円ツール: 1点目＝中心、2点目＝半径（グリッド）。線種はプロパティで変更。"
    )
    btn_sk_circle.setAccessibleName("円")

    btn_sk_cloud = QPushButton(parent)
    btn_sk_cloud.setCheckable(True)
    btn_sk_cloud.setObjectName("sketchToolCloud")
    btn_sk_cloud.setIcon(sketch_cloud_icon())
    btn_sk_cloud.setIconSize(_SK_ICO)
    btn_sk_cloud.setToolTip(
        "雲マーク: 左クリックで頂点を追加、ダブルクリックで確定。"
        " 始点をダブルクリックで閉じる／それ以外は開いた雲。"
        " 線種は選択後にプロパティで変更。"
    )
    btn_sk_cloud.setAccessibleName("雲マーク")

    btn_sk_text = QPushButton(parent)
    btn_sk_text.setCheckable(True)
    btn_sk_text.setObjectName("sketchToolText")
    btn_sk_text.setIcon(sketch_text_icon())
    btn_sk_text.setIconSize(_SK_ICO)
    btn_sk_text.setToolTip(
        "テキスト: クリックで配置（位置はスナップなし）。"
        " 文字・高さは選択後にプロパティで編集。"
    )
    btn_sk_text.setAccessibleName("テキスト")

    return WireSketchToolButtons(
        auto_wire=btn_auto,
        manual_wire=btn_manual,
        sk_line=btn_sk_line,
        sk_circle=btn_sk_circle,
        sk_cloud=btn_sk_cloud,
        sk_text=btn_sk_text,
    )
