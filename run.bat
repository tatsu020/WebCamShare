@echo off
echo Syncing dependencies...
uv sync
if %errorlevel% neq 0 (
    echo Error syncing dependencies.
    pause
    exit /b %errorlevel%
)

echo Starting application...
uv run main.py
if %errorlevel% neq 0 (
    echo Application exited with error.
    pause
)
