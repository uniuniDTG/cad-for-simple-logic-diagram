"""Tests for Markdown manual helpers and docs path resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

from logic_cad.docs_path import docs_directory
from logic_cad.ui.panels.manual_dialog import (
    EXCLUDED_MARKDOWN_NAMES,
    directory_base_url,
    list_markdown_files,
    markdown_source_to_html,
    resolve_manual_href_to_target,
)


def test_markdown_source_to_html_includes_heading_and_body() -> None:
    html = markdown_source_to_html("# Title\n\nHello.")
    assert "Title" in html
    assert "Hello" in html


def test_list_markdown_files_excludes_todo(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a.md").write_text("x", encoding="utf-8")
    (d / "TODO.md").write_text("y", encoding="utf-8")
    found = list_markdown_files(d)
    assert [p.name for p in found] == ["a.md"]


def test_excluded_constant_contains_todo() -> None:
    assert "TODO.md" in EXCLUDED_MARKDOWN_NAMES


def test_docs_directory_frozen_uses_meipass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    bundle_root = tmp_path / "bundle_root"
    bundle_root.mkdir()
    meipass_docs = bundle_root / "docs"
    meipass_docs.mkdir()
    (meipass_docs / "x.md").write_text("#", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_root), raising=False)
    assert docs_directory() == meipass_docs


def test_docs_directory_dev_points_at_repo_docs() -> None:
    d = docs_directory()
    assert d.name == "docs"
    assert (d / "developer.md").is_file()


def test_resolve_manual_href_to_target_sibling_md(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    base = docs / "developer.md"
    base.write_text("x", encoding="utf-8")
    target, frag = resolve_manual_href_to_target(base, "user_template_manual.md")
    assert target == (docs / "user_template_manual.md").resolve()
    assert frag is None


def test_resolve_manual_href_to_target_parent_path(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    pkg = tmp_path / "logic_cad"
    pkg.mkdir()
    base = docs / "developer.md"
    base.write_text("x", encoding="utf-8")
    target, frag = resolve_manual_href_to_target(base, "../logic_cad/docs_path.py")
    assert target == (pkg / "docs_path.py").resolve()
    assert frag is None


def test_resolve_manual_href_to_target_fragment_only(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    base = docs / "user_template_manual.md"
    base.write_text("x", encoding="utf-8")
    target, frag = resolve_manual_href_to_target(base, "#debug")
    assert target == base.resolve()
    assert frag == "debug"


def test_resolve_manual_href_to_target_backslashes(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    base = docs / "a.md"
    base.write_text("x", encoding="utf-8")
    target, frag = resolve_manual_href_to_target(base, r"b.md")
    assert target == (docs / "b.md").resolve()
    assert frag is None


def test_directory_base_url_resolves_relative_href(tmp_path: Path) -> None:
    d = tmp_path / "docs"
    d.mkdir()
    base = directory_base_url(d)
    resolved = base.resolved(QUrl("user_template_manual.md"))
    assert Path(resolved.toLocalFile()) == (d / "user_template_manual.md").resolve()
