"""Export paper layouts to PDF from the main window."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMessageBox, QProgressDialog

from logic_cad.core.services.pdf_export_service import PdfExportCancelled, export_paper_layouts_to_pdf
from logic_cad.ui.pdf_export_options_dialog import PdfExportOptionsDialog
from logic_cad.ui.toast import show_toast

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


def run_export_pdf(win: MainWindow) -> None:
    opt_dlg = PdfExportOptionsDialog(win._diagram, win)
    if opt_dlg.exec() != QDialog.DialogCode.Accepted:
        return
    pdf_opts = opt_dlg.options()

    path, _ = QFileDialog.getSaveFileName(
        win,
        "PDF にエクスポート",
        "",
        "PDF (*.pdf)",
    )
    if not path:
        return
    if not path.lower().endswith(".pdf"):
        path = path + ".pdf"
    pages = win._diagram.list_pages()
    dlg = QProgressDialog("PDF を書き出しています…", "キャンセル", 0, len(pages), win)
    dlg.setWindowModality(Qt.WindowModality.WindowModal)
    dlg.setMinimumDuration(0)
    dlg.setValue(0)

    def is_cancelled() -> bool:
        QApplication.processEvents()
        return dlg.wasCanceled()

    def on_progress(done: int, total: int) -> None:
        dlg.setMaximum(max(total, 1))
        dlg.setValue(done)
        QApplication.processEvents()

    try:
        export_paper_layouts_to_pdf(
            win._diagram.doc,
            path,
            layout_names=pages,
            progress_callback=on_progress,
            is_cancelled=is_cancelled,
            export_options=pdf_opts,
        )
    except PdfExportCancelled:
        dlg.reset()
        try:
            os.unlink(path)
        except OSError:
            pass
        QMessageBox.information(win, "PDF エクスポート", "キャンセルしました。")
        return
    except Exception as ex:
        dlg.reset()
        QMessageBox.warning(win, "PDF エクスポート", str(ex))
        return
    dlg.reset()
    show_toast(f"PDF を保存しました: {path}", parent_window=win, duration=8000)
