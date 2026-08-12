param(
    [ValidateSet("private", "public")]
    [string]$Visibility = "private",
    [string]$Repository = "telegram-workflow-desktop"
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required. Install it and run 'gh auth login' first."
}

gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated" }

if (-not (Test-Path .git)) {
    git init -b main
}

if (-not (git status --porcelain)) {
    Write-Output "Working tree has no uncommitted files."
} else {
    git add .
    git commit -m "bootstrap desktop workflow app"
}

$visibilityFlag = "--$Visibility"
gh repo create $Repository $visibilityFlag --source=. --remote=origin --push
