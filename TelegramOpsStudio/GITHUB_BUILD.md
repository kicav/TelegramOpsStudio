# GitHub build procedure

## 1. Repository contents

The repository root must contain:

```text
.github/workflows/windows-build.yml
app/
main.py
requirements.txt
requirements-dev.txt
pyproject.toml
scripts/
tests/
```

The workflow has an explicit layout-validation step so missing files fail with a readable error before `pip install`.

## 2. Push

```powershell
git add .
git commit -m "Telegram Ops Studio 1.0.0"
git push origin main
```

Open **Actions → Build Windows App**. A successful run produces an artifact named `TelegramOpsStudio-Windows-<commit-sha>`.

## 3. Release

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The same workflow verifies that the tag matches `APP_VERSION`, tests/builds again, and publishes `TelegramOpsStudio.exe`, `SHA256SUMS.txt` and `update-manifest.json` to the GitHub Release.

## 4. If a build fails

Open the failed step first. When Nuitka reaches compilation, the workflow also attempts to upload `nuitka-report.xml` or a crash report as a diagnostics artifact.

Do not add Telegram API Hash, OTP, 2FA password, `.session` files, databases, certificates or proxy passwords to GitHub Secrets unless a separate test specifically requires them. The default CI does not need Telegram credentials.
