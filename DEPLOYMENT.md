# Deployment

## Repository layout

The project files must be at repository root:

```text
.github/
src/
tests/
scripts/
packaging/
app.py
pyproject.toml
README.md
.gitignore
```

Do not upload this entire project as a second nested directory.

## CI

`CI` runs on pushes to `main` and pull requests:

1. Python 3.12
2. install package + dev dependencies
3. compile
4. Ruff
5. pytest
6. self-check

No Telegram credentials are required.

## Windows standalone

Run `Build Windows` manually or from a matching pull request. It:

1. installs Python 3.12 dependencies
2. runs tests
3. initializes the MSVC/dumpbin environment
4. generates `pysidedeploy.spec`
5. uses `standalone` mode
6. builds `TelegramOpsStudio.exe`
7. runs `--version`
8. runs `--self-check`
9. copies the complete standalone directory to `release/TelegramOpsStudio/`
10. removes PDB files
11. uploads the standalone artifact

## Release

Push a version tag only after CI and Windows build are green:

```text
v0.3.0
```

`Release Windows` creates:

```text
TelegramOpsStudio-Portable-v0.3.0.zip
TelegramOpsStudioSetup-0.3.0.exe
SHA256SUMS.txt
```

The release workflow does not require Telegram phone numbers, OTPs, API hashes or real sessions.
