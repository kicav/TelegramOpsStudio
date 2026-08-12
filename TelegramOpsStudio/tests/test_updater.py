from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from app import license_updater


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def test_update_version_comparison(monkeypatch):
    manifest = {
        "version": "1.1.0",
        "url": "https://example.test/app.exe",
        "sha256": "a" * 64,
    }
    monkeypatch.setattr(license_updater, "_fetch_json", lambda _url: manifest)
    result = license_updater.check_update("https://example.test/manifest.json")
    assert result["update_available"] is True


def test_verified_download(monkeypatch, tmp_path: Path):
    data = b"verified payload"
    digest = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(license_updater.urllib.request, "urlopen", lambda *_a, **_k: FakeResponse(data))
    destination = tmp_path / "app.exe"
    assert license_updater.download_verified("https://example.test/app.exe", digest, str(destination)) == digest
    assert destination.read_bytes() == data


def test_update_rejects_http():
    with pytest.raises(ValueError):
        license_updater.check_update("http://example.test/manifest.json")
