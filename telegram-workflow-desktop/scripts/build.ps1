$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

function Enable-MsvcEnvironment {
    if (Get-Command dumpbin.exe -ErrorAction SilentlyContinue) { return }

    $vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) {
        throw "dumpbin.exe not found and vswhere.exe is unavailable"
    }

    $installPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $installPath) { throw "Visual Studio C++ build tools were not found" }

    $vsDevCmd = Join-Path $installPath "Common7\Tools\VsDevCmd.bat"
    if (-not (Test-Path $vsDevCmd)) { throw "VsDevCmd.bat was not found at $vsDevCmd" }

    $envLines = cmd.exe /s /c "`"$vsDevCmd`" -arch=x64 -host_arch=x64 >nul && set"
    foreach ($line in $envLines) {
        if ($line.StartsWith("=")) { continue }
        $parts = $line -split "=", 2
        if ($parts.Count -eq 2) {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], "Process")
        }
    }

    if (-not (Get-Command dumpbin.exe -ErrorAction SilentlyContinue)) {
        throw "MSVC environment initialized but dumpbin.exe is still unavailable"
    }
}

Enable-MsvcEnvironment

if (Test-Path pysidedeploy.spec) { Remove-Item pysidedeploy.spec -Force }
if (Test-Path dist) { Remove-Item dist -Recurse -Force }

pyside6-deploy app.py --init --force
python scripts/configure_deploy_spec.py pysidedeploy.spec
pyside6-deploy -c pysidedeploy.spec --force --name TelegramWorkflow

$exe = Get-ChildItem -Path dist -Filter "TelegramWorkflow.exe" -Recurse | Select-Object -First 1
if (-not $exe) { throw "TelegramWorkflow.exe was not produced" }
& $exe.FullName --version
if ($LASTEXITCODE -ne 0) { throw "Built executable failed --version" }
& $exe.FullName --self-check
if ($LASTEXITCODE -ne 0) { throw "Built executable failed --self-check" }
Write-Output "Built: $($exe.FullName)"
