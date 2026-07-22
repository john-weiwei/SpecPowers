@echo off
REM SpecPowers deterministic layer launcher (Windows)
REM Thin batch — delegates all logic to bridge/facade.py
REM
REM Usage: bin\specpowers.bat <subcommand> [options]

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "BRIDGE_DIR=%SCRIPT_DIR%..\bridge"

REM Find Python — prefer managed Python from WorkBuddy, then system
set "PYTHON="

REM Check for managed Node workspace Python (if exists)
if exist "%LOCALAPPDATA%\..\..\workbuddy\binaries\python\versions" (
    for /f "delims=" %%i in ('dir /b /ad "%LOCALAPPDATA%\..\..\workbuddy\binaries\python\versions" 2^>nul ^| sort /r') do (
        if exist "%LOCALAPPDATA%\..\..\workbuddy\binaries\python\versions\%%i\python.exe" (
            set "PYTHON=%LOCALAPPDATA%\..\..\workbuddy\binaries\python\versions\%%i\python.exe"
            goto :found_python
        )
    )
)

REM Fallback: system Python
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set "PYTHON=python"
    goto :found_python
)

echo Error: Python 3.11+ not found in PATH
exit /b 2

:found_python
"%PYTHON%" "%BRIDGE_DIR%\facade.py" %*
exit /b %ERRORLEVEL%
