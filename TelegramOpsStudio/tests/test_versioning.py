from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_preflight_and_version_scripts_pass():
    for script in ("scripts/preflight.py", "scripts/check_version.py"):
        result = subprocess.run(
            [sys.executable, script], cwd=ROOT, text=True, capture_output=True, env={**os.environ, "GITHUB_REF_TYPE": ""}
        )
        assert result.returncode == 0, result.stdout + result.stderr
