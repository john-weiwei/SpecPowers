: << 'CMDBLOCK'
@echo off
REM 跨平台 polyglot 包装器（参考 superpowers 项目同名文件）。
REM Windows: cmd.exe 执行 batch 分支，查找并调用 bash。
REM Unix: shell 把本文件当脚本执行（: 在 bash 里是空操作）。
REM
REM Hook 脚本用无扩展名文件名（如 check-deps 而非 check-deps.sh），
REM 避免 Claude Code 在 Windows 上对含 .sh 的命令自动前缀 bash 造成干扰。
REM
REM 退出码透传约束：exit /b %ERRORLEVEL% 不能放在 if (...) 括号块内——
REM 括号块在解析期一次性展开 %ERRORLEVEL%（取到 bash 执行前的旧值），
REM 子脚本真实退出码被吞；本文件用 goto 平铺结构规避，且必须保持
REM CRLF 换行（goto 标签定位在 LF 文件中不可靠）。
REM
REM 用法: run-hook.cmd <script-name> [args...]

if "%~1"=="" (
    echo run-hook.cmd: missing script name >&2
    exit /b 1
)

set "HOOK_DIR=%~dp0"

REM 按优先级查找 Git for Windows bash
if exist "C:\Program Files\Git\bin\bash.exe" goto run_progfiles
if exist "C:\Program Files (x86)\Git\bin\bash.exe" goto run_progfiles_x86

REM 回退 PATH 上的 bash（用户自装的 Git Bash / MSYS2 / Cygwin），
REM 排除 C:\Windows\System32\bash.exe——那是 WSL 入口，执行 Windows 路径必然失败
set "BASH_EXE="
for /f "delims=" %%B in ('where bash 2^>nul') do (
    echo %%B | findstr /i "System32" >nul 2>nul
    if errorlevel 1 (set "BASH_EXE=%%B" & goto run_pathbash)
)

REM 无 bash —— 静默退出（插件仍可用，只是跳过 SessionStart 依赖提示注入）
exit /b 0

:run_progfiles
"C:\Program Files\Git\bin\bash.exe" "%HOOK_DIR%%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run_progfiles_x86
"C:\Program Files (x86)\Git\bin\bash.exe" "%HOOK_DIR%%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%

:run_pathbash
"%BASH_EXE%" "%HOOK_DIR%%~1" %2 %3 %4 %5 %6 %7 %8 %9
exit /b %ERRORLEVEL%
CMDBLOCK

# Unix 分支：直接运行指定脚本
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRIPT_NAME="$1"
shift
exec bash "${SCRIPT_DIR}/${SCRIPT_NAME}" "$@"
