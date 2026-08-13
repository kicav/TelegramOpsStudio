from __future__ import annotations

import argparse
import configparser
from pathlib import Path


def configure(path: Path) -> None:
    parser = configparser.ConfigParser(
        comment_prefixes=("#", ";"),
        allow_no_value=True,
        strict=False,
    )
    parser.read(path, encoding="utf-8")

    required = {"app", "python", "qt", "nuitka"}
    missing = sorted(required - set(parser.sections()))
    if missing:
        raise RuntimeError(f"Unexpected pysidedeploy.spec; missing sections: {missing}")

    parser.set("app", "title", "TelegramOpsStudio")
    parser.set("app", "project_dir", ".")
    parser.set("app", "input_file", str(Path("app.py").resolve()))
    parser.set("app", "exec_directory", str(Path("dist").resolve()))
    parser.set("nuitka", "mode", "standalone")
    parser.set(
        "nuitka",
        "extra_args",
        "--quiet --noinclude-qt-translations --assume-yes-for-downloads --output-filename=TelegramOpsStudio.exe"
    )

    with path.open("w", encoding="utf-8") as handle:
        parser.write(handle)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("spec", type=Path)
    args = cli.parse_args()
    configure(args.spec)
