"""Find-only and replace dialog for symbol LABEL/SYM and user annotation text."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Literal

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from logic_cad.core.logic_diagram import LogicDiagram
from logic_cad.core.pages.page_order import list_paper_layout_names_sorted
from logic_cad.core.services.text_find_replace import (
    list_text_search_hits,
    text_count_matches,
    text_find_replace,
)
from logic_cad.ui.text_search_navigate import apply_text_search_hit

if TYPE_CHECKING:
    from logic_cad.ui.main_window.window import MainWindow


class FindReplaceDialog(QDialog):
    """Modeless find or modal replace: navigation or replace-all on allowed symbol text / USER_TEXT."""

    def __init__(
        self,
        parent: QWidget | None,
        diagram: LogicDiagram,
        on_applied: Callable[[], None],
        mode: Literal["find", "replace"],
        main_window: MainWindow | None = None,
    ) -> None:
        """Build the find-only (modeless) or find-and-replace (modal) dialog.

        Args:
            parent: Parent widget.
            diagram: The active logic diagram.
            on_applied: Called after a successful replace. Unused for ``mode=find``.
            mode: ``find`` = search and jump; ``replace`` = replace all with undo.
            main_window: Required when ``mode=find`` for canvas navigation.
        """
        super().__init__(parent)
        self._is_find = mode == "find"
        if self._is_find:
            self.setModal(False)
        else:
            self.setModal(True)
        self._diagram = diagram
        self._on_applied = on_applied
        self._main_window: MainWindow | None = main_window
        self._n_sub: int | None = None
        self._search_cache_key: Any = None

        if mode == "find":
            self.setWindowTitle("文字列の検索")
        else:
            self.setWindowTitle("文字列の置換")

        self._edit_find = QLineEdit(self)
        self._edit_repl = QLineEdit(self)
        self._scope = QComboBox(self)
        self._scope.addItem("現在のページ", userData="current")
        self._scope.addItem("図面内の全用紙ページ", userData="all")
        self._use_regex = QCheckBox("正規表現を使う", self)
        self._use_regex.setChecked(False)
        self._use_regex.setTristate(False)
        self._case = QCheckBox("大文字と小文字を区別する", self)
        self._case.setChecked(False)
        self._case.setTristate(False)

        self._search_hits: list = []
        self._search_index = 0
        self._lbl_search_status = QLabel("")
        self._lbl_search_status.setStyleSheet("color: #888; font-size: 11px;")
        self._btn_prev: QPushButton | None = None
        self._btn_next: QPushButton | None = None
        self._btn_cancel: QPushButton | None = None
        self._sc_next: QShortcut | None = None
        self._sc_prev: QShortcut | None = None

        foot_lines = [
            "図枠（表題・図番・Rev 等）、STATIC_LABEL*、目次、ページ/シート内参照のラベルは対象外です。",
        ]
        if mode == "find":
            foot_lines.append(
                "「次検索」で一致へ移動（初回は検索、以降は次へ）。F3 / Shift+F3 も可（パネルを閉じても"
                "メイン画面にフォーカスがあれば同じ）。検索語が空のときは何もしません。"
            )
            foot_lines.append(
                "検索ワードと各オプション（正規表現・大文字小文字・範囲）は図面には保存されず、このセッション内の表示のみです。"
            )
        if mode == "replace":
            foot_lines.append("")
        foot = QLabel("\n".join(foot_lines))
        foot.setWordWrap(True)
        foot.setStyleSheet("color: #888; font-size: 11px;")

        form = QFormLayout()
        if mode == "find":
            form.addRow("検索:", self._edit_find)
        else:
            form.addRow("検索:", self._edit_find)
            form.addRow("置換:", self._edit_repl)
        form.addRow("範囲:", self._scope)

        v = QVBoxLayout(self)
        v.addLayout(form)
        v.addWidget(self._use_regex)
        v.addWidget(self._case)
        if mode == "find":
            v.addWidget(self._lbl_search_status)
        v.addWidget(foot)

        row = QHBoxLayout()
        row.addStretch(1)
        if mode == "find":
            self._btn_prev = QPushButton("前検索", self)
            self._btn_prev.setEnabled(False)
            self._btn_prev.clicked.connect(self._on_prev_search)
            self._btn_next = QPushButton("次検索", self)
            self._btn_next.clicked.connect(self._on_next_search)
            self._btn_cancel = QPushButton("キャンセル", self)
            self._btn_cancel.clicked.connect(self._on_cancel_find)
            row.addWidget(self._btn_prev)
            row.addWidget(self._btn_next)
            row.addWidget(self._btn_cancel)
            self._sc_next = QShortcut(QKeySequence("F3"), self)
            self._sc_next.activated.connect(self._on_next_search)
            self._sc_prev = QShortcut(QKeySequence("Shift+F3"), self)
            self._sc_prev.activated.connect(self._on_prev_search)
        else:
            self._btn_run = QPushButton("すべて置換", self)
            self._btn_run.clicked.connect(self._on_replace_all)
            self._btn_close = QPushButton("閉じる", self)
            self._btn_close.clicked.connect(self.reject)
            row.addWidget(self._btn_run)
            row.addWidget(self._btn_close)
        v.addLayout(row)

        if mode == "find":
            self._edit_repl.setVisible(False)
            self._edit_find.textChanged.connect(self._refresh_find_nav_buttons)
            self._scope.currentIndexChanged.connect(self._refresh_find_nav_buttons)
            self._use_regex.toggled.connect(self._refresh_find_nav_buttons)
            self._case.toggled.connect(self._refresh_find_nav_buttons)

    def set_diagram(self, diagram: LogicDiagram) -> None:
        """Point at the current document (e.g. after File / New) and clear stale hit list in find mode.

        When the same ``LogicDiagram`` instance is passed again (e.g. every F3 via ``_ensure_find_dialog``),
        the search result cache is **not** reset so next/prev can cycle. Only a **different** diagram
        (new/open document) clears hits.

        Args:
            diagram: The diagram shown in the main window.
        """
        if diagram is self._diagram:
            return
        self._diagram = diagram
        if self._is_find:
            self._search_hits = []
            self._search_index = 0
            self._search_cache_key = None
            self._n_sub = None
            self._update_search_hit_ui()

    def _current_search_key(self) -> tuple:
        """Tuple used to see if the user changed search options since last list_text_search_hits."""
        return (
            self._edit_find.text(),
            int(self._scope.currentIndex()),
            bool(self._use_regex.isChecked()),
            bool(self._case.isChecked()),
        )

    def closeEvent(self, event) -> None:
        """In find mode, hide instead of closing so the same panel can be reshown (Ctrl+F)."""
        if self._is_find:
            event.ignore()
            self._on_cancel_find()
        else:
            super().closeEvent(event)

    def reject(self) -> None:
        """Esc in find mode hides the panel; replace mode defers to QDialog."""
        if self._is_find:
            self._on_cancel_find()
        else:
            super().reject()

    def _on_cancel_find(self) -> None:
        """Hide the modeless find panel and return focus to the main window."""
        self.hide()
        if self._main_window is not None:
            self._main_window.activateWindow()

    def _layout_names_for_scope(self) -> list[str]:
        """Return paper layout name list according to the scope combobox.

        Returns:
            Non-model layout names to scan.
        """
        key = self._scope.currentData()
        if key == "all":
            return list_paper_layout_names_sorted(self._diagram.doc)
        return [self._diagram.current_layout_name]

    def _match_case(self) -> bool:
        """True when the search is case-sensitive (no ``re.IGNORECASE``)."""
        return bool(self._case.isChecked())

    def _refresh_find_nav_buttons(self) -> None:
        """``前検索`` is only valid for the current result set (search options may invalidate)."""
        if not self._is_find or self._btn_prev is None:
            return
        n = len(self._search_hits)
        k = self._current_search_key()
        ok = n > 0 and self._search_cache_key == k
        self._btn_prev.setEnabled(ok)

    def _update_search_hit_ui(self, n_sub: int | None = None) -> None:
        """Update status and ``前検索`` enable from ``_search_hits`` and ``_search_index``."""
        n = len(self._search_hits)
        if n == 0:
            self._lbl_search_status.setText("")
            self._refresh_find_nav_buttons()
            return
        if n_sub is not None:
            self._n_sub = n_sub
        if self._n_sub is not None:
            self._lbl_search_status.setText(
                f"一致: {self._n_sub} 箇所 — 表示 {self._search_index + 1} / {n}"
            )
        else:
            self._lbl_search_status.setText(f"表示 {self._search_index + 1} / {n} 箇所目")
        self._refresh_find_nav_buttons()

    def trigger_next_search(self) -> None:
        """Find mode: same as 次検索 (used from MainWindow when the panel is hidden)."""
        if self._is_find:
            self._on_next_search()

    def trigger_prev_search(self) -> None:
        """Find mode: same as 前検索 (used from MainWindow when the panel is hidden)."""
        if self._is_find:
            self._on_prev_search()

    def _on_prev_search(self) -> None:
        """Move to the previous hit (wraps). Requires a current result set matching search options."""
        if not self._edit_find.text().strip():
            return
        if not self._search_hits or self._main_window is None:
            return
        if self._search_cache_key != self._current_search_key():
            return
        self._search_index = (self._search_index - 1) % len(self._search_hits)
        apply_text_search_hit(self._main_window, self._search_hits[self._search_index])
        self._update_search_hit_ui()

    def _on_next_search(self) -> None:
        """If options changed or no hits, resolve list and go to first; else go to next hit."""
        if not self._edit_find.text().strip():
            return
        if self._main_window is None:
            QMessageBox.warning(
                self,
                "検索",
                "内部エラー: メインウィンドウが無いため表示を移動できません。",
            )
            return
        key = self._current_search_key()
        if (not self._search_hits) or (self._search_cache_key != key):
            self._run_search_refresh()
            return
        self._search_index = (self._search_index + 1) % len(self._search_hits)
        apply_text_search_hit(self._main_window, self._search_hits[self._search_index])
        self._update_search_hit_ui()

    def _run_search_refresh(self) -> None:
        """Recompute hit list, jump to the first, update cache (same query options)."""
        if self._main_window is None:
            return
        pat = self._edit_find.text()
        layout_names = self._layout_names_for_scope()
        use_regex = bool(self._use_regex.isChecked())
        mc = self._match_case()
        key = self._current_search_key()
        try:
            self._search_hits = list_text_search_hits(
                self._diagram,
                layout_names,
                pat,
                match_case=mc,
                use_regex=use_regex,
            )
        except re.error as e:
            QMessageBox.warning(
                self,
                "正規表現",
                f"パターンが無効です: {e}",
            )
            return
        self._search_cache_key = key
        if not self._search_hits:
            self._search_index = 0
            self._n_sub = None
            self._update_search_hit_ui()
            QMessageBox.information(self, "検索", "一致する文字列はありませんでした。")
            return
        self._search_index = 0
        n_sub = text_count_matches(
            self._diagram,
            layout_names,
            pat,
            match_case=mc,
            use_regex=use_regex,
        )
        apply_text_search_hit(self._main_window, self._search_hits[0])
        self._update_search_hit_ui(n_sub=n_sub)

    def _on_replace_all(self) -> None:
        """Run dry-run then replace in one undo transaction when matches exist."""
        pat = self._edit_find.text()
        repl = self._edit_repl.text()
        use_regex = bool(self._use_regex.isChecked())
        layout_names = self._layout_names_for_scope()
        mc = self._match_case()
        try:
            n_dry = text_find_replace(
                self._diagram,
                layout_names,
                pat,
                repl,
                match_case=mc,
                use_regex=use_regex,
                apply=False,
            )
        except re.error as e:
            QMessageBox.warning(
                self,
                "正規表現",
                f"パターンが無効です: {e}",
            )
            return
        if n_dry == 0:
            QMessageBox.information(self, "検索", "一致する文字列はありませんでした。")
            return
        with self._diagram.begin("文字列の検索/置換"):
            n = text_find_replace(
                self._diagram,
                layout_names,
                pat,
                repl,
                match_case=mc,
                use_regex=use_regex,
                apply=True,
            )
        self._on_applied()
        QMessageBox.information(self, "置換", f"{n} 箇所を置換しました。")
