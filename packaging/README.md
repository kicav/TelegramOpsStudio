# Packaging

`windows_installer.iss` packages the stable standalone directory produced by `scripts/build.ps1`:

```text
release/TelegramOpsStudio/
```

Build order:

```powershell
./scripts/build.ps1
./scripts/build_installer.ps1 -Version 0.2.0
```

Do not package session files, runtime databases, logs, exports, `.env` files or PDB symbols.
