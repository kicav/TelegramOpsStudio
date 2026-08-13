param(
    [string]$Repository = "kicav/TelegramOpsStudio",
    [string]$Branch = "main"
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "GitHub CLI (gh) is required"
}
gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated" }

if (-not (Test-Path .git)) {
    git init -b $Branch
    git remote add origin "https://github.com/$Repository.git"
}

python -m compileall -q src tests app.py
pytest
if ($LASTEXITCODE -ne 0) { throw "Tests failed; refusing to push" }

git add -A
if (git status --porcelain) {
    git commit -m "rebuild TelegramOpsStudio architecture"
}
git push -u origin $Branch
