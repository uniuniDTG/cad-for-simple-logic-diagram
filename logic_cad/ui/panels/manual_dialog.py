"""In-app Markdown manual: file list and HTML preview (QTextBrowser)."""

from __future__ import annotations

from pathlib import Path

import markdown
from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from logic_cad.docs_path import docs_directory, docs_dir_exists

# Internal / scratchpad Markdown not shown in the end-user manual browser.
EXCLUDED_MARKDOWN_NAMES: frozenset[str] = frozenset({"TODO.md"})


def list_markdown_files(root: Path) -> list[Path]:
    """Return sorted ``*.md`` files directly under ``root``, excluding internal names.

    Args:
        root: Directory to scan (typically ``docs_directory()``).

    Returns:
        Sorted paths (case-insensitive by basename). Missing or non-directory ``root``
        yields an empty list.
    """
    if not root.is_dir():
        return []
    found: list[Path] = []
    for p in root.glob("*.md"):
        if p.is_file() and p.name not in EXCLUDED_MARKDOWN_NAMES:
            found.append(p)
    found.sort(key=lambda x: x.name.lower())
    return found


def markdown_source_to_html(source: str, *, title: str = "") -> str:
    """Convert Markdown source to a minimal HTML document for ``QTextBrowser``.

    Args:
        source: Markdown text.
        title: Optional ``<title>`` for the HTML shell.

    Returns:
        Full HTML document string.
    """
    md = markdown.Markdown(extensions=["fenced_code", "tables", "nl2br"])
    body = md.convert(source)
    style = """<style>
body { font-family: 'Segoe UI', 'Yu Gothic UI', sans-serif; font-size: 14px;
  color: #e8e8ec; background-color: #2b2f36; margin: 8px; }
code { font-family: Consolas, 'Courier New', monospace; background: #1e2128; padding: 1px 4px;
  border-radius: 3px; }
pre { font-family: Consolas, 'Courier New', monospace; background: #1e2128; padding: 8px;
  border-radius: 4px; overflow-x: auto; }
pre code { background: transparent; padding: 0; }
a { color: #6eb8e0; }
table { border-collapse: collapse; margin: 0.5em 0; }
th, td { border: 1px solid #4a5058; padding: 4px 8px; }
</style>"""
    title_html = f"<title>{title}</title>" if title else ""
    return f"<html><head><meta charset=\"utf-8\">{title_html}{style}</head><body>{body}</body></html>"


def directory_base_url(directory: Path) -> QUrl:
    """Build a ``file://`` URL for a directory (trailing separator for relative link resolution).

    Args:
        directory: Absolute or resolved directory path.

    Returns:
        Local ``QUrl`` suitable for ``QTextDocument.setBaseUrl``.
    """
    d = directory.resolve()
    # QTextDocument resolves relative hrefs against this base; a directory must end with /.
    return QUrl.fromLocalFile(str(d) + "/")


def resolve_manual_href_to_target(base_file: Path, href: str) -> tuple[Path, str | None]:
    """Resolve a manual hyperlink string relative to the current Markdown file (testable).

    Normalizes backslashes in the path segment so ``docs\\\\foo.md``-style hrefs still join.

    Args:
        base_file: The ``.md`` file currently displayed.
        href: Raw ``href`` (e.g. ``user_manual.md``, ``../logic_cad/x.py``, ``#anchor``).

    Returns:
        ``(resolved_absolute_path, fragment_or_none)``. For same-document links (``#a`` or empty
        path before ``#``), ``path`` is ``base_file`` resolved.
    """
    s = href.strip()
    if "#" in s:
        path_part, _, frag = s.partition("#")
        fragment = frag if frag else None
    else:
        path_part, fragment = s, None
    path_part = path_part.replace("\\", "/").strip()
    if path_part == "":
        return base_file.resolve(), fragment
    target = (base_file.parent / path_part).resolve()
    return target, fragment


class ManualDialog(QDialog):
    """Non-modal window: left file list, right Markdown preview."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("マニュアル")
        self.setModal(False)
        self.resize(880, 620)

        root = QVBoxLayout(self)
        hint = QLabel("左の一覧から Markdown ファイルを選ぶと、右にプレビューします。")
        hint.setWordWrap(True)
        root.addWidget(hint)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self._list = QListWidget()
        self._list.setMinimumWidth(200)
        self._browser = QTextBrowser()
        # Resolve relative ``<a href>`` via ``setBaseUrl``; navigation is handled in ``_on_anchor_clicked``.
        self._browser.setOpenLinks(False)
        self._browser.setOpenExternalLinks(False)
        self._browser.anchorClicked.connect(self._on_anchor_clicked)
        self._current_doc_path: Path | None = None
        splitter.addWidget(self._list)
        splitter.addWidget(self._browser)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([240, 640])
        root.addWidget(splitter, 1)

        self._list.currentItemChanged.connect(self._on_current_item_changed)

        self._reload_file_list()

    def refresh(self) -> None:
        """Re-scan the manuals directory and update the list (call before ``show()``)."""
        self._reload_file_list()

    def _reload_file_list(self) -> None:
        """Populate the list from ``docs_directory()``."""
        self._list.clear()
        self._browser.clear()
        self._current_doc_path = None
        if not docs_dir_exists():
            self._browser.setPlainText(
                "マニュアル用の docs フォルダが見つかりません。\n"
                "開発時はリポジトリ直下の docs を、PyInstaller 実行時はバンドル datas を確認してください。"
            )
            return

        root = docs_directory()
        paths = list_markdown_files(root)
        if not paths:
            self._browser.setPlainText("表示できる Markdown ファイルがありません。")
            return

        for p in paths:
            item = QListWidgetItem(p.name)
            item.setData(Qt.ItemDataRole.UserRole, p)
            self._list.addItem(item)
        self._list.setCurrentRow(0)

    def _on_current_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            self._browser.clear()
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, Path):
            return
        self._load_path(data)

    def _is_navigable_manual_md(self, path: Path) -> bool:
        """Return whether ``path`` is an in-app manual (flat ``docs/*.md``, not excluded).

        Args:
            path: Candidate filesystem path.

        Returns:
            True if the file exists, lives directly under ``docs_directory()``, is ``*.md``,
            and is not in ``EXCLUDED_MARKDOWN_NAMES``.
        """
        root = docs_directory()
        if not path.is_file():
            return False
        if path.parent.resolve() != root.resolve():
            return False
        if path.suffix.lower() != ".md":
            return False
        if path.name in EXCLUDED_MARKDOWN_NAMES:
            return False
        return True

    def _select_list_row_for_path(self, path: Path) -> bool:
        """Select the sidebar row that points at ``path``.

        Args:
            path: Absolute manual file path.

        Returns:
            True if a matching list item existed and the row was selected.
        """
        for i in range(self._list.count()):
            item = self._list.item(i)
            data = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, Path) and data.resolve() == path.resolve():
                self._list.setCurrentRow(i)
                return True
        return False

    def _schedule_scroll_to_anchor(self, fragment: str) -> None:
        """Scroll to ``fragment`` after the browser finishes laying out new HTML.

        Args:
            fragment: HTML anchor name (without ``#``).
        """

        def _scroll() -> None:
            self._browser.scrollToAnchor(fragment)

        QTimer.singleShot(0, _scroll)

    def _select_and_show_manual(self, path: Path, fragment: str | None) -> None:
        """Load a navigable manual file and optionally jump to a fragment.

        Args:
            path: Resolved ``*.md`` under the manuals root.
            fragment: Optional in-document anchor, or None.
        """
        if not self._is_navigable_manual_md(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            return
        if self._select_list_row_for_path(path):
            if fragment:
                self._schedule_scroll_to_anchor(fragment)
            return
        self._load_path(path)
        if fragment:
            self._schedule_scroll_to_anchor(fragment)

    def _on_anchor_clicked(self, url: QUrl) -> None:
        """Handle link activation from the preview (external URLs vs in-app ``*.md``).

        Args:
            url: Target from ``anchorClicked`` (possibly relative to the document base URL).
        """
        if url.scheme() in ("http", "https"):
            QDesktopServices.openUrl(url)
            return
        if url.scheme() == "mailto":
            QDesktopServices.openUrl(url)
            return

        base = self._browser.document().baseUrl()
        resolved = base.resolved(url) if base.isValid() else url
        if resolved.scheme() in ("http", "https"):
            QDesktopServices.openUrl(resolved)
            return

        local = resolved.toLocalFile()
        if not local:
            if url.hasFragment():
                self._browser.scrollToAnchor(url.fragment(QUrl.ComponentFormattingOption.FullyDecoded))
            return

        path = Path(local)
        fragment: str | None = None
        if resolved.hasFragment():
            fragment = resolved.fragment(QUrl.ComponentFormattingOption.FullyDecoded)

        current = self._current_doc_path
        if current is not None and path.resolve() == current.resolve():
            if fragment:
                self._browser.scrollToAnchor(fragment)
            return

        if path.suffix.lower() == ".md" and self._is_navigable_manual_md(path):
            self._select_and_show_manual(path, fragment)
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _load_path(self, path: Path) -> None:
        """Load ``path`` into the preview widget."""
        self._current_doc_path = path.resolve()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as ex:
            QMessageBox.warning(
                self,
                "マニュアル",
                f"ファイルを読み込めませんでした。\n{path}\n\n{ex}",
            )
            self._browser.setPlainText("")
            return
        html = markdown_source_to_html(text, title=path.name)
        self._browser.document().setBaseUrl(directory_base_url(path.parent))
        self._browser.setHtml(html)
