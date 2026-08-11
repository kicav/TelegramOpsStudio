from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path

from .config import APP_VERSION


def read_license(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"valid": False, "message": "License file not found"}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"valid": False, "message": f"Invalid JSON: {e}"}
    # Community build: license metadata is informational. Production builds should verify a detached signature.
    return {"valid": bool(obj.get("licensee")), "message": obj.get("licensee", "Unnamed"), "data": obj}


def check_update(manifest_url: str) -> dict:
    if not manifest_url.lower().startswith("https://"):
        raise ValueError("Update manifest must use HTTPS")
    with urllib.request.urlopen(manifest_url, timeout=10) as r:
        manifest = json.loads(r.read().decode("utf-8"))
    required = {"version", "url", "sha256"}
    if not required.issubset(manifest):
        raise ValueError("Manifest requires version, url and sha256")
    return {**manifest, "current_version": APP_VERSION, "update_available": manifest["version"] != APP_VERSION}


def download_verified(url: str, sha256_hex: str, destination: str) -> str:
    if not url.lower().startswith("https://"):
        raise ValueError("Download URL must use HTTPS")
    data = urllib.request.urlopen(url, timeout=30).read()
    digest = hashlib.sha256(data).hexdigest().lower()
    if digest != sha256_hex.lower():
        raise ValueError("SHA-256 mismatch; update rejected")
    Path(destination).write_bytes(data)
    return digest
