from __future__ import annotations

import os
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project_version = str(pyproject["project"]["version"])
    config_text = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'^APP_VERSION\s*=\s*["\']([^"\']+)["\']', config_text, re.MULTILINE)
    if not match:
        raise SystemExit("APP_VERSION not found in app/config.py")
    app_version = match.group(1)
    if project_version != app_version:
        raise SystemExit(f"Version mismatch: pyproject={project_version}, app={app_version}")

    tag = os.environ.get("GITHUB_REF_NAME", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    if ref_type == "tag" and tag.startswith("v") and tag[1:] != app_version:
        raise SystemExit(f"Release tag {tag} does not match application version {app_version}")

    print(f"VERSION_OK {app_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
