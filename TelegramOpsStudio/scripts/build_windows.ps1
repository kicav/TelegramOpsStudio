$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$required = @("main.py", "requirements.txt", "requirements-dev.txt", "app/db.py", "app/ui.py")
foreach ($file in $required) {
    if (-not (Test-Path $file)) { throw "Required file is missing: $file" }
}

python scripts/preflight.py
python scripts/check_version.py

python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip check
python -m compileall -q main.py app scripts tests
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q

python main.py --self-test
$env:QT_QPA_PLATFORM = "offscreen"
python main.py --ui-self-test

New-Item -ItemType Directory -Force -Path dist | Out-Null
python -m nuitka `
    --mode=onefile `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --msvc=latest `
    --output-dir=dist `
    --output-filename=TelegramOpsStudio.exe `
    --include-package=keyring.backends `
    --include-package=win32ctypes `
    --product-name="Telegram Ops Studio" `
    --file-description="Telegram Ops Studio" `
    --file-version=1.0.0.0 `
    --product-version=1.0.0.0 `
    --report=dist/nuitka-report.xml `
    --assume-yes-for-downloads `
    main.py

if (-not (Test-Path "dist/TelegramOpsStudio.exe")) {
    throw "Build failed: dist/TelegramOpsStudio.exe was not created."
}

& "dist/TelegramOpsStudio.exe" --self-test
if ($LASTEXITCODE -ne 0) { throw "Built executable runtime self-test failed: $LASTEXITCODE" }
$env:QT_QPA_PLATFORM = "offscreen"
& "dist/TelegramOpsStudio.exe" --ui-self-test
if ($LASTEXITCODE -ne 0) { throw "Built executable UI self-test failed: $LASTEXITCODE" }

$hash = (Get-FileHash "dist/TelegramOpsStudio.exe" -Algorithm SHA256).Hash.ToLower()
"$hash  TelegramOpsStudio.exe" | Set-Content -Encoding ascii "dist/SHA256SUMS.txt"
Write-Host "Build complete: dist/TelegramOpsStudio.exe"
Get-Content "dist/SHA256SUMS.txt"
