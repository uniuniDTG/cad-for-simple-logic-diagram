"""Application-wide Qt stylesheet for the main window and its descendants."""

from __future__ import annotations

from pathlib import Path


def _asset_uri(filename: str) -> str:
    """Return an absolute stylesheet asset path in POSIX form."""
    return (Path(__file__).resolve().parent / "assets" / filename).as_posix()


_CHECKBOX_UNCHECKED_URI = _asset_uri("checkbox_unchecked.svg")
_CHECKBOX_CHECKED_URI = _asset_uri("checkbox_checked.svg")


_APP_STYLESHEET_TEMPLATE = """
QMainWindow, QWidget { background-color: #252830; color: #d8d8dc; font-family: "__APP_FONT_FAMILY__", sans-serif; font-size: 9pt; }

QStatusBar {
    background-color: #1e2026;
    color: #c8d0dc;
    border-top: 1px solid #1a1c20;
    padding: 2px 6px;
    font-size: 9pt;
}
QStatusBar::item { border: none; }
QStatusBar QLabel#statusCursorCoords {
    color: #b8c0d0;
    font-family: "Consolas", "Cascadia Mono", monospace;
    padding: 0 2px 0 6px;
}

QMenuBar, QMenu { background-color: #343840; color: #e8e8ec; border: none; }
QMenuBar::item { padding: 4px 8px; }
QMenuBar::item:selected, QMenu::item:selected { background-color: #3a8ab8; color: #ffffff; }
QMenu { border: 1px solid #1a1c20; }
QMenu::item { padding: 4px 20px 4px 12px; }
QMenu::separator { height: 1px; background-color: #303540; margin: 2px 0; }

QTreeWidget, QListWidget {
    background-color: #2e3138;
    border: 1px solid #1a1c20;
    color: #e0e0e4;
    outline: none;
}
QListWidget::item { padding: 3px 6px; border-bottom: 1px solid #22252b; }
QListWidget::item:hover { background-color: #343840; color: #ffffff; }
QListWidget::item:selected { background-color: #1e3a5a; color: #c8e8ff; border-left: 2px solid #3a8ab8; }
QTreeWidget::item:hover { background-color: #343840; }
QTreeWidget::item:selected { background-color: #1e3a5a; color: #c8e8ff; }

QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #1e2026;
    border: 1px solid #383c44;
    border-radius: 1px;
    color: #e8e8ec;
    padding: 2px 4px;
    font-family: "Consolas", "Cascadia Mono", monospace;
    font-size: 9pt;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #3a8ab8;
}
QComboBox {
    background-color: #1e2026;
    border: 1px solid #383c44;
    border-radius: 1px;
    color: #e8e8ec;
    padding: 2px 4px;
}
QComboBox:focus { border: 1px solid #3a8ab8; }
QComboBox::drop-down { border: none; width: 18px; }
QComboBox QAbstractItemView {
    background-color: #2e3138;
    border: 1px solid #1a1c20;
    color: #e0e0e4;
    selection-background-color: #1e3a5a;
}

QPushButton {
    background-color: #2e4e78;
    color: #e8eaed;
    padding: 4px 12px;
    border: 1px solid #3a6090;
    border-radius: 1px;
}
QPushButton:hover { background-color: #3a5e8a; border-color: #4a78a8; }
QPushButton:pressed { background-color: #1e3a5a; }
QPushButton:disabled { background-color: #2a2c30; color: #606470; border-color: #303540; }

QCheckBox {
    spacing: 6px;
}
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #4a5060;
    border-radius: 2px;
    background-color: #1e2026;
    image: url("__CHECKBOX_UNCHECKED_URI__");
}
QCheckBox::indicator:hover {
    border-color: #6a7084;
    background-color: #242832;
}
QCheckBox::indicator:checked {
    border-color: #0d5f78;
    background-color: #007aa0;
    image: url("__CHECKBOX_CHECKED_URI__");
}
QCheckBox::indicator:disabled {
    border-color: #303540;
    background-color: #1a1c20;
}
QCheckBox::indicator:checked:disabled {
    background-color: #2a4a58;
}

QWidget#paletteColumn QPushButton#wireToolAuto,
QWidget#paletteColumn QPushButton#wireToolManual {
    background-color: #2e3138;
    color: #c8ccd4;
    text-align: left;
    padding: 6px 10px;
    border: 1px solid #383c44;
    border-radius: 0px;
    border-left: 3px solid #383c44;
}
QWidget#paletteColumn QPushButton#wireToolAuto:hover,
QWidget#paletteColumn QPushButton#wireToolManual:hover {
    background-color: #343840;
    border-color: #4a5060;
    border-left-color: #4a5060;
    color: #e8eaed;
}
QWidget#paletteColumn QPushButton#wireToolAuto:checked,
QWidget#paletteColumn QPushButton#wireToolManual:checked {
    background-color: #3a2200;
    color: #ffc070;
    border: 1px solid #7a4a00;
    border-left: 3px solid #ff9030;
}
QWidget#paletteColumn QPushButton#wireToolAuto:checked:hover,
QWidget#paletteColumn QPushButton#wireToolManual:checked:hover {
    background-color: #4a2c00;
    border-color: #9a6010;
    border-left-color: #ffaa50;
}

QWidget#paletteColumn QPushButton#sketchToolLine,
QWidget#paletteColumn QPushButton#sketchToolCircle,
QWidget#paletteColumn QPushButton#sketchToolArc,
QWidget#paletteColumn QPushButton#sketchToolCloud,
QWidget#paletteColumn QPushButton#sketchToolText {
    background-color: #2e3138;
    border: 1px solid #383c44;
    border-radius: 0px;
    padding: 4px;
    min-width: 38px;
    max-width: 38px;
    min-height: 34px;
    max-height: 34px;
}
QWidget#paletteColumn QPushButton#sketchToolLine:hover,
QWidget#paletteColumn QPushButton#sketchToolCircle:hover,
QWidget#paletteColumn QPushButton#sketchToolArc:hover,
QWidget#paletteColumn QPushButton#sketchToolCloud:hover,
QWidget#paletteColumn QPushButton#sketchToolText:hover {
    background-color: #343840;
    border-color: #4a7a98;
}
QWidget#paletteColumn QPushButton#sketchToolLine:checked,
QWidget#paletteColumn QPushButton#sketchToolCircle:checked,
QWidget#paletteColumn QPushButton#sketchToolArc:checked,
QWidget#paletteColumn QPushButton#sketchToolCloud:checked,
QWidget#paletteColumn QPushButton#sketchToolText:checked {
    background-color: #003a52;
    border: 2px solid #00b4e0;
}
QWidget#paletteColumn QPushButton#sketchToolLine:checked:hover,
QWidget#paletteColumn QPushButton#sketchToolCircle:checked:hover,
QWidget#paletteColumn QPushButton#sketchToolArc:checked:hover,
QWidget#paletteColumn QPushButton#sketchToolCloud:checked:hover,
QWidget#paletteColumn QPushButton#sketchToolText:checked:hover {
    background-color: #00485e;
    border-color: #30c8f0;
}

QWidget#blockEditPanel QPushButton#blockSketchToolLine,
QWidget#blockEditPanel QPushButton#blockSketchToolCircle,
QWidget#blockEditPanel QPushButton#blockSketchToolArc,
QWidget#blockEditPanel QPushButton#blockSketchToolText,
QWidget#blockEditPanel QPushButton#blockSketchToolAttdef,
QWidget#blockEditPanel QPushButton#blockSketchToolPlainText,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPort,
QFrame#blockEditToolsBar QPushButton#blockSketchToolLine,
QFrame#blockEditToolsBar QPushButton#blockSketchToolCircle,
QFrame#blockEditToolsBar QPushButton#blockSketchToolArc,
QFrame#blockEditToolsBar QPushButton#blockSketchToolText,
QFrame#blockEditToolsBar QPushButton#blockSketchToolAttdef,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPlainText {
    background-color: #2e3138;
    border: 1px solid #383c44;
    border-radius: 0px;
    padding: 4px;
    min-width: 38px;
    max-width: 38px;
    min-height: 34px;
    max-height: 34px;
}
QWidget#blockEditPanel QPushButton#blockSketchToolLine:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolCircle:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolArc:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolText:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolAttdef:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolPlainText:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPort:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolLine:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolCircle:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolArc:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolText:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolAttdef:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPlainText:hover {
    background-color: #343840;
    border-color: #4a7a98;
}
QWidget#blockEditPanel QPushButton#blockSketchToolLine:checked,
QWidget#blockEditPanel QPushButton#blockSketchToolCircle:checked,
QWidget#blockEditPanel QPushButton#blockSketchToolArc:checked,
QWidget#blockEditPanel QPushButton#blockSketchToolText:checked,
QWidget#blockEditPanel QPushButton#blockSketchToolAttdef:checked,
QWidget#blockEditPanel QPushButton#blockSketchToolPlainText:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPort:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolLine:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolCircle:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolArc:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolText:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolAttdef:checked,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPlainText:checked {
    background-color: #003a52;
    border: 2px solid #00b4e0;
}
QWidget#blockEditPanel QPushButton#blockSketchToolLine:checked:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolCircle:checked:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolArc:checked:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolText:checked:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolAttdef:checked:hover,
QWidget#blockEditPanel QPushButton#blockSketchToolPlainText:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPort:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolLine:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolCircle:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolArc:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolText:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolAttdef:checked:hover,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPlainText:checked:hover {
    background-color: #00485e;
    border-color: #30c8f0;
}
QFrame#blockEditToolsBar QPushButton#blockApplyToMain {
    background-color: #1a5c42;
    color: #e8f8ee;
    border: 1px solid #2a8c60;
    padding: 6px 14px;
    min-width: 120px;
    max-width: none;
    min-height: 28px;
    max-height: none;
    font-weight: bold;
}
QFrame#blockEditToolsBar QPushButton#blockApplyToMain:hover {
    background-color: #228050;
    border-color: #40b878;
}
QFrame#blockEditToolsBar QPushButton#blockApplyToMain:pressed {
    background-color: #0d4028;
}

QWidget#blockEditPanel QPushButton#blockSketchToolCircle:disabled,
QWidget#blockEditPanel QPushButton#blockSketchToolText:disabled,
QWidget#blockEditPanel QPushButton#blockSketchToolAttdef:disabled,
QWidget#blockEditPanel QPushButton#blockSketchToolPlainText:disabled,
QFrame#blockEditToolsBar QPushButton#blockSketchToolCircle:disabled,
QFrame#blockEditToolsBar QPushButton#blockSketchToolText:disabled,
QFrame#blockEditToolsBar QPushButton#blockSketchToolAttdef:disabled,
QFrame#blockEditToolsBar QPushButton#blockSketchToolPlainText:disabled {
    background-color: #26282e;
    border-color: #2e3238;
}

QGraphicsView {
    border: 1px solid #1a1c20;
    border-top: 2px solid #1a1c20;
    background-color: #23252a;
}

/* Block symbol editor: opaque style sheet background would hide scene drawBackground (grid). */
QGraphicsView#blockEditCanvasView {
    border: 1px solid #1a1c20;
    border-top: 2px solid #1a1c20;
    background-color: transparent;
}

QGroupBox {
    font-weight: bold;
    font-size: 9pt;
    border: 1px solid #383c44;
    border-left: 3px solid #3a8ab8;
    border-radius: 0px;
    margin-top: 12px;
    padding-top: 6px;
}
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; color: #8ab0d0; }

QLabel#hint { color: #7a8090; font-size: 9pt; }
QLabel#sectionHeader {
    color: #7a8090;
    font-size: 8pt;
    font-weight: bold;
    letter-spacing: 1px;
    padding: 2px 0px 3px 0px;
    border-bottom: 1px solid #303540;
}

QFrame#sectionSep {
    background-color: #303540;
    max-height: 1px;
    border: none;
    margin: 2px 0px;
}

QListWidget#symbolPalette::item:selected { background-color: transparent; color: #e0e0e4; border-left: none; }
QListWidget#symbolPalette::item:hover { background-color: #343840; color: #ffffff; }

QTabWidget::pane { border: 1px solid #1a1c20; background-color: #2e3138; }
QTabWidget::pane { border-top: 2px solid #3a8ab8; }
QTabBar::tab {
    background-color: #2e3138;
    color: #9098a8;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #1a1c20;
}
QTabBar::tab:selected { background-color: #252830; color: #d8e8f8; border-right: 1px solid #1a1c20; border-left: 2px solid #3a8ab8; }
QTabBar::tab:hover:!selected { background-color: #343840; color: #c8d0dc; }

QScrollBar:vertical {
    background-color: #1e2026;
    width: 8px;
    border: none;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background-color: #404550;
    border-radius: 3px;
    min-height: 24px;
    margin: 1px;
}
QScrollBar::handle:vertical:hover { background-color: #505868; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

QScrollBar:horizontal {
    background-color: #1e2026;
    height: 8px;
    border: none;
    margin: 0px;
}
QScrollBar::handle:horizontal {
    background-color: #404550;
    border-radius: 3px;
    min-width: 24px;
    margin: 1px;
}
QScrollBar::handle:horizontal:hover { background-color: #505868; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: none; }

QSplitter::handle { background-color: #1a1c20; }
QSplitter::handle:horizontal { width: 2px; }
QSplitter::handle:vertical { height: 2px; }
QSplitter::handle:hover { background-color: #3a8ab8; }

QToolTip {
    background-color: #1e2026;
    color: #c8d0dc;
    border: 1px solid #383c44;
    padding: 4px 6px;
    font-size: 9pt;
}

QDialog { background-color: #252830; }
QDialogButtonBox QPushButton { min-width: 72px; }

QProgressDialog { background-color: #252830; }
QProgressBar {
    background-color: #1e2026;
    border: 1px solid #383c44;
    border-radius: 1px;
    text-align: center;
    color: #c8d0dc;
    height: 12px;
}
QProgressBar::chunk { background-color: #3a8ab8; border-radius: 1px; }
""".strip()

def build_app_stylesheet() -> str:
    """Build the application stylesheet with resolved UI font family.

    Must be called after ``QApplication`` exists (uses :func:`~logic_cad.ui.app_font.resolve_app_ui_font_family`).

    Returns:
        Complete Qt stylesheet string.
    """
    from logic_cad.ui.app_font import resolve_app_ui_font_family

    family = resolve_app_ui_font_family()
    return (
        _APP_STYLESHEET_TEMPLATE.replace("__CHECKBOX_UNCHECKED_URI__", _CHECKBOX_UNCHECKED_URI)
        .replace("__CHECKBOX_CHECKED_URI__", _CHECKBOX_CHECKED_URI)
        .replace("__APP_FONT_FAMILY__", family)
    )


# Legacy import path: prefer :func:`build_app_stylesheet` after QApplication is created.
APP_STYLESHEET = _APP_STYLESHEET_TEMPLATE.replace(
    "__CHECKBOX_UNCHECKED_URI__", _CHECKBOX_UNCHECKED_URI
).replace("__CHECKBOX_CHECKED_URI__", _CHECKBOX_CHECKED_URI).replace(
    "__APP_FONT_FAMILY__", "sans-serif"
)
