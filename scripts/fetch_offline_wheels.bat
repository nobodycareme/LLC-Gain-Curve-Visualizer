@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

REM ===================================================================
REM  下载离线 wheel 到 offline_wheels\
REM
REM  用途：在一台能上网的 Windows 机器上运行本脚本，把所有依赖的
REM        .whl 文件抓到 offline_wheels\ 目录；随后可以把整个工程
REM        目录拷到没有网络的机器上，build_exe.bat 会自动优先使用
REM        offline_wheels\ 里的离线包安装，无需联网。
REM
REM  说明：wheel 是"平台相关"的二进制包。本脚本抓取的是
REM        win_amd64 平台的包，只能用于 64 位 Windows。
REM ===================================================================

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJ=%%~fI"
set "WHEELS=%PROJ%\offline_wheels"
set "REQ=%PROJ%\requirements.txt"

echo ============================================================
echo  工程根目录 : "%PROJ%"
echo  wheel 输出 : "%WHEELS%"
echo ============================================================

if not exist "%REQ%" (
    echo [错误] 找不到 requirements.txt : "%REQ%"
    exit /b 1
)

REM ---- 找一个可用的 64 位 Python ----
set "HOSTPY="
for %%V in (3.11 3.12 3.10) do (
    if not defined HOSTPY (
        py -%%V-64 -c "import sys;sys.exit(0)" >nul 2>&1
        if !errorlevel! equ 0 set "HOSTPY=py -%%V-64"
    )
)
if not defined HOSTPY (
    python -c "import sys;sys.exit(0 if sys.maxsize>2**32 else 1)" >nul 2>&1
    if !errorlevel! equ 0 set "HOSTPY=python"
)
if not defined HOSTPY (
    echo [错误] 未找到 64 位 Python 3.10/3.11/3.12。
    echo         请先安装：https://www.python.org/downloads/windows/
    exit /b 1
)
echo [信息] 使用 Python: !HOSTPY!

if not exist "%WHEELS%" mkdir "%WHEELS%"

REM ---- 可选：使用国内镜像加速（默认启用清华源，注释掉即用官方源） ----
set "IDX=-i https://pypi.tuna.tsinghua.edu.cn/simple"
REM set "IDX="

echo.
echo [1/2] 升级 pip / wheel ...
!HOSTPY! -m pip install --upgrade pip wheel %IDX%
if errorlevel 1 (
    echo [警告] pip 升级失败，继续尝试下载。
)

echo.
echo [2/2] 下载依赖 wheel 到 offline_wheels\ ...
REM --only-binary=:all: 保证只拿预编译 wheel，避免目标机需要编译器
!HOSTPY! -m pip download --only-binary=:all: -r "%REQ%" -d "%WHEELS%" %IDX%
if errorlevel 1 (
    echo.
    echo [错误] 下载失败。常见原因：
    echo         - 网络不通或代理设置问题
    echo         - 某个包在当前 Python 版本下没有 win_amd64 预编译包
    echo         可尝试：改用官方源（把脚本里的 IDX 置空）后重试。
    exit /b 1
)

echo.
echo ============================================================
echo  下载完成，offline_wheels\ 内容：
echo ============================================================
dir /b "%WHEELS%\*.whl"
echo.
for /f %%C in ('dir /b "%WHEELS%\*.whl" 2^>nul ^| find /c /v ""') do echo  共 %%C 个 wheel 文件
echo.
echo  现在可以把整个工程目录拷到离线机器，运行 scripts\build_exe.bat
echo ============================================================
endlocal
exit /b 0
