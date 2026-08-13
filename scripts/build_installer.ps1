param([string]$Version = "0.2.0")
$ErrorActionPreference = "Stop"

$iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $iscc) {
    $default = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $default) { $iscc = Get-Item $default }
}
if (-not $iscc) {
    throw "Inno Setup 6 (ISCC.exe) is required to build the installer"
}

& $iscc.Source "/DAppVersion=$Version" "packaging\windows_installer.iss"
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
