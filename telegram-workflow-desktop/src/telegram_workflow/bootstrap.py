from __future__ import annotations

import argparse
import sys

from telegram_workflow.diagnostics.self_check import format_self_check_json, run_self_check
from telegram_workflow.version import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="TelegramWorkflow")
    parser.add_argument("--version", action="store_true", help="Print version and exit")
    parser.add_argument("--self-check", action="store_true", help="Run local diagnostics and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.version:
        print(__version__)
        return 0

    if args.self_check:
        ok, results = run_self_check()
        print(format_self_check_json(results))
        return 0 if ok else 1

    from PySide6.QtWidgets import QApplication

    from telegram_workflow.runtime.core_runtime import CoreRuntime
    from telegram_workflow.ui.main_window import MainWindow

    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    runtime = CoreRuntime()
    window = MainWindow(runtime)

    def shutdown() -> None:
        runtime.request_stop()
        runtime.wait(3000)

    app.aboutToQuit.connect(shutdown)
    runtime.start()
    window.show()
    return app.exec()
