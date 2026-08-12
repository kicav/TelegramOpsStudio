from pathlib import Path


def test_ci_files_are_present():
    root = Path(__file__).resolve().parents[1]
    required = [
        root / "requirements.txt",
        root / "requirements-dev.txt",
        root / ".github" / "workflows" / "windows-build.yml",
        root / "scripts" / "build_windows.ps1",
        root / "scripts" / "preflight.py",
        root / "scripts" / "check_version.py",
    ]
    missing = [str(path.relative_to(root)) for path in required if not path.exists()]
    assert not missing, f"Missing CI files: {missing}"


def test_workflow_uses_module_pytest_and_required_files():
    root = Path(__file__).resolve().parents[1]
    text = (root / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
    assert "python -m pytest" in text
    assert "requirements-dev.txt" in text
    assert "TelegramOpsStudio.exe" in text
    assert "Source runtime self-tests" in text
    assert "actions/checkout@v6" in text
    assert "actions/setup-python@v6" in text
    assert "actions/upload-artifact@v7" in text
    assert "Project preflight and version consistency" in text
    assert "update-manifest.json" in text
    assert "--ui-self-test" in text
