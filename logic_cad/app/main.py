"""Qt application entry point."""

from __future__ import annotations

import argparse
import os
import sys

from PySide6.QtWidgets import QApplication

from logic_cad.core.routing.profile import ENV_ROUTING_FIXED, ENV_ROUTING_OVG
from logic_cad.ui.app_user_settings import APP_DISPLAY_NAME, APP_ORG_NAME
from logic_cad.ui.main_window import MainWindow


def main() -> None:
    ap = argparse.ArgumentParser(description="Logic CAD")
    ap.add_argument(
        "--debug",
        action="store_true",
        help="標準出力に [logic_cad:…] ログ（環境変数 LOGIC_CAD_DEBUG=1 と同じ）",
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
    if args.debug:
        os.environ["LOGIC_CAD_DEBUG"] = "1"
        os.environ["LOGIC_CAD_DEBUG_ROUTING_VERBOSE"] = "1"
    if args.routing_manhattan_only:
        os.environ[ENV_ROUTING_OVG] = "0"
        os.environ.pop(ENV_ROUTING_FIXED, None)
    elif args.routing_ovg_only:
        os.environ[ENV_ROUTING_FIXED] = "0"
        os.environ.pop(ENV_ROUTING_OVG, None)

    app = QApplication(sys.argv)
    app.setOrganizationName(APP_ORG_NAME)
    app.setApplicationName(APP_DISPLAY_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
