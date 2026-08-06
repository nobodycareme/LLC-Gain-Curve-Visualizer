@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

REM requirements.txt 为 UTF-8 编码；在中文(GBK)区域设置下
REM pip 默认用 GBK 读取会报 UnicodeDecodeError，这里强制 UTF-8 模式。
set "PYTHONUTF8=1"

REM ===================================================================
REM  从源码运行 LLC 增益曲线（不打包）
REM  自动定位工程目录、按需创建 .venv、安装依赖后启动 GUI
REM ===================================================================

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJ=%%~fI"
cd /d "%PROJ%" || (echo [错误] 无法进入工程目录 & exit /b 1)

set "VENV=%PROJ%\.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "VPYW=%VENV%\Scripts\pythonw.exe"

if not exist "%VPY%" (
    echo [提示] 未找到虚拟环境，正在创建 ...
    set "HOSTPY="
    for %%V in (3.11 3.12 3.10) do (
        if not defined HOSTPY (
            py -%%V-64 -c "import os,sysconfig,sys;sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()['stdlib'],'venv','__main__.py')) and sys.maxsize>2**32 else 1)" >nul 2>&1
            if !errorlevel! equ 0 set "HOSTPY=py -%%V-64"
        )
    )
    if not defined HOSTPY (
        python -c "import os,sysconfig,sys;sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()['stdlib'],'venv','__main__.py')) and sys.maxsize>2**32 and (3,10)<=sys.version_info<(3,13) else 1)" >nul 2>&1
        if !errorlevel! equ 0 set "HOSTPY=python"
    )
    if not defined HOSTPY (
        echo [错误] 未找到 64 位 Python 3.10 - 3.12
        echo        请先安装: winget install -e --id Python.Python.3.11
        exit /b 2
    )
    !HOSTPY! -m venv "%VENV%" || (echo [错误] 创建虚拟环境失败 & exit /b 3)
)

REM 依赖缺失时自动安装
"%VPY%" -c "import PySide6, numpy, matplotlib" >nul 2>&1
if !errorlevel! neq 0 (
    echo [提示] 正在安装依赖 ...
    "%VPY%" -m pip install --quiet --upgrade pip >nul 2>&1
    if exist "%PROJ%\offline_wheels\*.whl" (
        "%VPY%" -m pip install --quiet --no-index --find-links "%PROJ%\offline_wheels" -r "%PROJ%\requirements.txt"
    )
    "%VPY%" -c "import PySide6, numpy, matplotlib" >nul 2>&1
    if !errorlevel! neq 0 (
        "%VPY%" -m pip install -r "%PROJ%\requirements.txt" || (echo [错误] 依赖安装失败 & exit /b 4)
    )
)

echo 启动 LLC 增益曲线 (源码模式) ...
if exist "%VPYW%" (
    start "" "%VPYW%" "%PROJ%\src\main.py"
) else (
    "%VPY%" "%PROJ%\src\main.py"
)
endlocal
exit /b 0
