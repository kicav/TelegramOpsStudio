# GitHub deployment & Windows build

This repository is configured to build `TelegramOpsStudio.exe` automatically with GitHub Actions.

## 1. Create the GitHub repository

Recommended repository name: `TelegramOpsStudio`.

During initial testing, use a **Private** repository. Do not commit Telegram `.session` files, API hashes, databases, certificates, or other credentials.

## 2. Push the source

From PowerShell in the project directory:

```powershell
git init
git branch -M main
git add .
git commit -m "Initial Telegram Ops Studio release"
git remote add origin https://github.com/<YOUR_USERNAME>/TelegramOpsStudio.git
git push -u origin main
```

The workflow `.github/workflows/windows-build.yml` starts automatically.

## 3. Download the Windows app

Open the GitHub repository, then:

`Actions` → `Build Windows App` → latest successful run → `Artifacts` → download `TelegramOpsStudio-Windows-...`.

The artifact contains:

- `TelegramOpsStudio.exe`
- `SHA256SUMS.txt`

## 4. Create a release

Create and push a version tag:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The same workflow builds the app and creates/updates a GitHub Release with the executable and SHA-256 file.

## Security rules

Never commit:

- `*.session`
- `*.session-journal`
- API hash / OTP / 2FA password
- `.env`
- SQLite databases
- signing certificates or private keys

The included `.gitignore` blocks these common files.
