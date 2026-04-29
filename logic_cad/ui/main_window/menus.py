"""Main window menu bar (File / Edit / Project settings / …)."""

from __future__ import annotations

from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QMainWindow


def build_file_edit_menus(w: QMainWindow) -> None:
    m_file = w.menuBar().addMenu("ファイル")
    a_new = QAction("新規", w)
    a_new.triggered.connect(w._new_doc)  # type: ignore[attr-defined]
    m_file.addAction(a_new)
    a_open = QAction("開く…", w)
    a_open.triggered.connect(w._open_doc)  # type: ignore[attr-defined]
    m_file.addAction(a_open)
    a_save = QAction("保存", w)
    a_save.setShortcut(QKeySequence.StandardKey.Save)
    a_save.triggered.connect(w._save_doc)  # type: ignore[attr-defined]
    m_file.addAction(a_save)
    a_save_as = QAction("名前を付けて保存…", w)
    a_save_as.triggered.connect(w._save_as_doc)  # type: ignore[attr-defined]
    m_file.addAction(a_save_as)
    a_pdf = QAction("PDFにエクスポート…", w)
    a_pdf.triggered.connect(w._export_pdf)  # type: ignore[attr-defined]
    m_file.addAction(a_pdf)
    m_file.addSeparator()
    a_user = QAction("ユーザ設定…", w)
    a_user.triggered.connect(w._user_settings)  # type: ignore[attr-defined]
    m_file.addAction(a_user)

    m_edit = w.menuBar().addMenu("編集")
    a_undo = QAction("&Undo", w)
    a_undo.setShortcut(QKeySequence.StandardKey.Undo)
    a_undo.triggered.connect(w._undo)  # type: ignore[attr-defined]
    m_edit.addAction(a_undo)
    a_redo = QAction("&Redo", w)
    a_redo.setShortcut(QKeySequence.StandardKey.Redo)
    a_redo.triggered.connect(w._redo)  # type: ignore[attr-defined]
    m_edit.addAction(a_redo)
    a_del = QAction("削除", w)
    a_del.setShortcut(QKeySequence.StandardKey.Delete)
    a_del.triggered.connect(w._delete_selection)  # type: ignore[attr-defined]
    m_edit.addAction(a_del)
    a_copy = QAction("コピー", w)
    a_copy.setShortcut(QKeySequence.StandardKey.Copy)
    a_copy.triggered.connect(w._copy_symbol_selection)  # type: ignore[attr-defined]
    m_edit.addAction(a_copy)
    a_paste = QAction("貼り付け", w)
    a_paste.setShortcut(QKeySequence.StandardKey.Paste)
    a_paste.triggered.connect(w._paste_symbol_clipboard)  # type: ignore[attr-defined]
    m_edit.addAction(a_paste)
    a_find = QAction("検索…", w)
    a_find.setShortcut(QKeySequence.StandardKey.Find)
    a_find.triggered.connect(w._show_find)  # type: ignore[attr-defined]
    m_edit.addAction(a_find)
    a_repl = QAction("置換…", w)
    a_repl.setShortcut(QKeySequence("Ctrl+R"))
    a_repl.triggered.connect(w._show_replace)  # type: ignore[attr-defined]
    m_edit.addAction(a_repl)
    m_edit.addSeparator()
    a_del_clouds = QAction("雲マークをすべて削除…", w)
    a_del_clouds.triggered.connect(w._delete_all_user_clouds)  # type: ignore[attr-defined]
    m_edit.addAction(a_del_clouds)


def build_project_settings_menu(w: QMainWindow) -> None:
    m_proj = w.menuBar().addMenu("プロジェクト設定")
    a_dwg = QAction("図面プロパティ…", w)
    a_dwg.triggered.connect(w._drawing_properties)  # type: ignore[attr-defined]
    m_proj.addAction(a_dwg)
    a_lw = QAction("レイヤ線設定…", w)
    a_lw.triggered.connect(w._edit_layer_lineweight)  # type: ignore[attr-defined]
    m_proj.addAction(a_lw)
    a_pf = QAction("優先フォント…", w)
    a_pf.triggered.connect(w._preferred_font_settings)  # type: ignore[attr-defined]
    m_proj.addAction(a_pf)


def build_template_menu(w: QMainWindow) -> None:
    m_tpl = w.menuBar().addMenu("テンプレート")
    a_frame = QAction("dxfから図枠テンプレートを読み込み…", w)
    a_frame.triggered.connect(w._apply_frame_template)  # type: ignore[attr-defined]
    m_tpl.addAction(a_frame)
    a_load_lib = QAction("dxfからシンボルライブラリを読み込み…", w)
    a_load_lib.triggered.connect(w._load_symbol_library_from_dxf)  # type: ignore[attr-defined]
    m_tpl.addAction(a_load_lib)
    a_reload_lib = QAction("シンボルライブラリを再読み込み", w)
    a_reload_lib.triggered.connect(w._reload_symbol_library)  # type: ignore[attr-defined]
    #m_tpl.addAction(a_reload_lib)


def build_view_menu(w: QMainWindow) -> None:
    m_view = w.menuBar().addMenu("表示")
    a_log = QAction("ログ…", w)
    a_log.triggered.connect(w._show_log_window)  # type: ignore[attr-defined]
    m_view.addAction(a_log)
    a_lib = QAction("シンボル一覧…", w)
    a_lib.triggered.connect(w._show_symbol_library)  # type: ignore[attr-defined]
    m_view.addAction(a_lib)
    a_manual = QAction("マニュアル…", w)
    a_manual.triggered.connect(w._show_manual)  # type: ignore[attr-defined]
    m_view.addAction(a_manual)
