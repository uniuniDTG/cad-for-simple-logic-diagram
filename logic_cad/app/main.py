"""Qt application entry point."""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtWidgets import QApplication

from logic_cad.core.routing.profile import ENV_ROUTING_FIXED, ENV_ROUTING_OVG
from logic_cad.ui.app_user_settings import APP_DISPLAY_NAME, APP_ORG_NAME
from logic_cad.ui.logging import install_process_stream_capture, install_python_logging_bridge
from logic_cad.ui.main_window import MainWindow


def main() -> None:
    ap = argparse.ArgumentParser(description="Logic CAD")
    ap.add_argument(
        "--debug",
        action="store_true",
        help="root logger レベルを DEBUG にして詳細ログを有効化する",
    )
    ro = ap.add_mutually_exclusive_group()
    ro.add_argument(
        "--routing-manhattan-only",
        action="store_true",
        help=(
            "デバッグ用: 固定マンハッタン段のみ（OVG マルチを無効化）。"
            "将来削除される可能性あり。"
        ),
    )
    ro.add_argument(
        "--routing-ovg-only",
        action="store_true",
        help=(
            "デバッグ用: OVG マルチのみ（固定マンハッタン段を無効化）。"
            "将来削除される可能性あり。"
        ),
    )
    args = ap.parse_args()
    if args.routing_manhattan_only:
        os.environ[ENV_ROUTING_OVG] = "0"
        os.environ.pop(ENV_ROUTING_FIXED, None)
    elif args.routing_ovg_only:
        os.environ[ENV_ROUTING_FIXED] = "0"
        os.environ.pop(ENV_ROUTING_OVG, None)

    install_process_stream_capture(forward_to_original=True)
    default_level = "DEBUG" if args.debug else os.environ.get("LOGIC_CAD_LOG_LEVEL", "WARN")
    install_python_logging_bridge(default_level=default_level)
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG_NAME)
    app.setApplicationName(APP_DISPLAY_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
