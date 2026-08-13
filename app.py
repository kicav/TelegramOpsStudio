from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path


def _load_main() -> Callable[[list[str] | None], int]:
    """Load the application entrypoint from an installed package or a source checkout."""
    source_dir = Path(__file__).resolve().parent / "src"
    if source_dir.is_dir():
        source_path = str(source_dir)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)

    from telegram_workflow.bootstrap import main

    return main


if __name__ == "__main__":
    raise SystemExit(_load_main()())
