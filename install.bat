@echo off
:: install.bat — Dataset Generator installer for Windows
:: Supports Windows Command Prompt and PowerShell
setlocal enabledelayedexpansion

echo.
echo  Dataset Generator - Windows Installer
echo  =====================================
echo.

:: ── Find Python 3.9+ ──────────────────────────────────────────────────────────
set PYTHON=
for %%c in (python python3 python3.13 python3.12 python3.11 python3.10 python3.9) do (
    if not defined PYTHON (
        where %%c >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=*" %%v in ('%%c -c "import sys; print(sys.version_info.major)" 2^>nul') do set PY_MAJOR=%%v
            for /f "tokens=*" %%v in ('%%c -c "import sys; print(sys.version_info.minor)" 2^>nul') do set PY_MINOR=%%v
            if !PY_MAJOR! geq 3 (
                if !PY_MINOR! geq 9 (
                    set PYTHON=%%c
                    for /f "tokens=*" %%v in ('%%c -c "import sys; print(f\"{sys.version_info.major}.{sys.version_info.minor}\")" 2^>nul') do set PY_VERSION=%%v
                )
            )
        )
    )
)

if not defined PYTHON (
    echo  [ERROR] Python 3.9+ not found.
    echo          Download and install it from https://python.org
    echo          Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)
echo  [OK] Python !PY_VERSION!  (!PYTHON!)

:: ── Create virtual environment ─────────────────────────────────────────────────
if exist ".venv" (
    echo  [OK] Virtual environment already exists — skipping creation.
) else (
    echo  Creating virtual environment...
    !PYTHON! -m venv .venv
    if !errorlevel! neq 0 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] Created .venv
)

:: ── Install dependencies ───────────────────────────────────────────────────────
echo  Installing dependencies...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if !errorlevel! neq 0 (
    echo  [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)
echo  [OK] Dependencies installed

:: ── Verify ─────────────────────────────────────────────────────────────────────
python -c "import tqdm" >nul 2>&1
if !errorlevel! equ 0 (
    echo  [OK] tqdm OK
) else (
    echo  [WARN] tqdm import failed - progress bars will be text-only
)

:: ── Done ───────────────────────────────────────────────────────────────────────
echo.
echo  Installation complete!
echo.
echo  Usage:
echo    .venv\Scripts\activate
echo    python generate.py --help
echo    python generate.py --dry-run
echo    python generate.py --scale 0.01 --output C:\path\to\storage
echo.
pause
