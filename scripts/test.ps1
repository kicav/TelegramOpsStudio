$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"
python -m compileall -q src tests app.py
ruff check src tests app.py
pytest
python -m telegram_workflow --self-check
