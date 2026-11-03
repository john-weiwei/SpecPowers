@echo off
REM SpecPowers facade wrapper (Windows) - invoked by agent skills/commands.
REM NOTE: keep this file ASCII-only. cmd.exe decodes batch files using the
REM active code page (cp936 on zh-CN Windows); non-ASCII comments in UTF-8
REM break tokenization and the whole script fails to run.
REM Package location strategy (three-level fallback):
REM   1. python -m specpowers_cli.bridge.facade (pip-installed, direct hit)
REM   2. embedded package: two levels up from bin/ is specpowers_cli/, add its parent to PYTHONPATH
REM   3. legacy local package copied by init (backward compat)

setlocal enabledelayedexpansion

REM Force UTF-8 on the Python side. This script is called by agents via pipes
REM (decoded as UTF-8); without it Python uses locale (cp936) for stdout and
REM crashes on non-ASCII output characters.
set "PYTHONUTF8=1"

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
REM Plugin layout: scripts\specpowers_cli\bin\specpowers.bat
REM   two levels up from bin\ = scripts\specpowers_cli\ (package root);
REM   add its parent (scripts\) to PYTHONPATH
set "EMBEDDED_PKG_PARENT=%SCRIPT_DIR%\..\.."

set "PYTHON=%SPECPOWERS_PYTHON%"
if "%PYTHON%"=="" set "PYTHON=python"

REM 1. Try the pip-installed package first
"%PYTHON%" -c "import specpowers_cli" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

REM 2. Embedded package: add scripts\ to PYTHONPATH
if exist "%EMBEDDED_PKG_PARENT%\specpowers_cli\__init__.py" (
    set "PYTHONPATH=%EMBEDDED_PKG_PARENT%;%PYTHONPATH%"
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

REM 3. Legacy compat: local package copied by init (skills\specpowers\specpowers_cli\)
set "LEGACY_PKG_ROOT=%SCRIPT_DIR%\.."
if exist "%LEGACY_PKG_ROOT%\specpowers_cli\__init__.py" (
    set "PYTHONPATH=%LEGACY_PKG_ROOT%"
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

echo Error: specpowers_cli package not found. >&2
echo   Tried: >&2
echo     1. python -m specpowers_cli (pip install) >&2
echo     2. %EMBEDDED_PKG_PARENT%\specpowers_cli\ (embedded package) >&2
echo   Fix: pip install -e . or reinstall the plugin >&2
exit /b 2
