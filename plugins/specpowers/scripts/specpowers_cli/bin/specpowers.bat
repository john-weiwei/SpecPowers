@echo off
REM SpecPowers facade 包装脚本（Windows）—— 由 agent slash 命令调用。
REM 包定位策略（三重兜底）：
REM   1. 优先 python -m specpowers_cli.bridge.facade（pip 全局安装时直接命中）
REM   2. 插件内嵌包：bin/ 的上两级是 specpowers_cli/ 包，其父目录加入 PYTHONPATH
REM   3. 旧版 init 拷贝的本地包（向后兼容）

setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
REM 去掉末尾反斜杠
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
REM 插件布局：scripts\specpowers_cli\bin\specpowers.bat
REM   bin\ 上两级 = scripts\specpowers_cli\（包根），其父目录 scripts\ 加入 PYTHONPATH
set "EMBEDDED_PKG_PARENT=%SCRIPT_DIR%\..\.."

set "PYTHON=%SPECPOWERS_PYTHON%"
if "%PYTHON%"=="" set "PYTHON=python"

REM 1. 尝试用已安装的包运行
"%PYTHON%" -c "import specpowers_cli" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

REM 2. 插件内嵌包：把 scripts\ 加入 PYTHONPATH
if exist "%EMBEDDED_PKG_PARENT%\specpowers_cli\__init__.py" (
    set "PYTHONPATH=%EMBEDDED_PKG_PARENT%;%PYTHONPATH%"
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

REM 3. 旧版兼容：init 拷贝的本地包（skills\specpowers\specpowers_cli\）
set "LEGACY_PKG_ROOT=%SCRIPT_DIR%\.."
if exist "%LEGACY_PKG_ROOT%\specpowers_cli\__init__.py" (
    set "PYTHONPATH=%LEGACY_PKG_ROOT%"
    "%PYTHON%" -m specpowers_cli.bridge.facade %*
    exit /b !ERRORLEVEL!
)

echo Error: specpowers_cli 包未找到。 >&2
echo   已尝试路径： >&2
echo     1. python -m specpowers_cli（pip 安装） >&2
echo     2. %EMBEDDED_PKG_PARENT%\specpowers_cli\（插件内嵌包） >&2
echo   修复方法：pip install -e . 或重新安装插件 >&2
exit /b 2
