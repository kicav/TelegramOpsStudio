param([Parameter(Mandatory=$true)][string]$ExePath)
$ErrorActionPreference = "Stop"
& $ExePath --version
if ($LASTEXITCODE -ne 0) { throw "--version failed" }
& $ExePath --self-check
if ($LASTEXITCODE -ne 0) { throw "--self-check failed" }
