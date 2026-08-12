from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from packaging.version import InvalidVersion, Version

from .config import APP_VERSION


def read_license(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"valid": False, "message": "License file not found"}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"valid": False, "message": f"Invalid JSON: {exc}"}
    # Community build: informational metadata only. A paid production build should verify a detached signature.
    return {"valid": bool(obj.get("licensee")), "message": obj.get("licensee", "Unnamed"), "data": obj}


def _fetch_json(url: str, timeout: int = 10) -> dict:
    if not url.lower().startswith("https://"):
        raise ValueError("URL must use HTTPS")
    request = urllib.request.Request(url, headers={"User-Agent": "TelegramOpsStudio-Updater/1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check_update(manifest_url: str) -> dict:
    if not manifest_url.strip():
        raise ValueError("Update manifest URL is not configured")
    manifest = _fetch_json(manifest_url)
    required = {"version", "url", "sha256"}
    if not required.issubset(manifest):
        raise ValueError("Manifest requires version, url and sha256")
    if not str(manifest["url"]).lower().startswith("https://"):
        raise ValueError("Manifest download URL must use HTTPS")
    digest = str(manifest["sha256"]).strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError("Manifest sha256 must be a 64-character hexadecimal digest")
    try:
        current = Version(APP_VERSION)
        remote = Version(str(manifest["version"]))
    except InvalidVersion as exc:
        raise ValueError("Manifest contains an invalid version") from exc
    return {
        **manifest,
        "current_version": APP_VERSION,
        "update_available": remote > current,
    }


def download_verified(url: str, sha256_hex: str, destination: str) -> str:
    if not url.lower().startswith("https://"):
        raise ValueError("Download URL must use HTTPS")
    digest_expected = sha256_hex.strip().lower()
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".part")

    request = urllib.request.Request(url, headers={"User-Agent": "TelegramOpsStudio-Updater/1"})
    hasher = hashlib.sha256()
    try:
        with urllib.request.urlopen(request, timeout=30) as response, tmp.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                handle.write(chunk)
        digest = hasher.hexdigest().lower()
        if digest != digest_expected:
            raise ValueError("SHA-256 mismatch; update rejected")
        tmp.replace(target)
        return digest
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
