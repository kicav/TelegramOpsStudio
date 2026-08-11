$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

python -m compileall -q main.py app scripts tests
python -m pytest tests -q

python -m nuitka `
    --mode=onefile `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --output-dir=dist `
    --output-filename=TelegramOpsStudio.exe `
    --include-package=keyring.backends `
    --assume-yes-for-downloads `
    main.py

if (-not (Test-Path "dist/TelegramOpsStudio.exe")) {
    throw "Build failed: dist/TelegramOpsStudio.exe was not created."
}

$hash = (Get-FileHash "dist/TelegramOpsStudio.exe" -Algorithm SHA256).Hash.ToLower()
"$hash  TelegramOpsStudio.exe" | Set-Content -Encoding ascii "dist/SHA256SUMS.txt"

Write-Host "Build complete: dist/TelegramOpsStudio.exe"
Get-Content "dist/SHA256SUMS.txt"
