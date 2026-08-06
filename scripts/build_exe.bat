@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

REM requirements.txt 为 UTF-8 编码；在中文(GBK)区域设置下
REM pip 默认用 GBK 读取会报 UnicodeDecodeError，这里强制 UTF-8 模式。
set "PYTHONUTF8=1"

REM 若环境设置了 SOCKS 代理(如 ALL_PROXY)而虚拟环境未装 pysocks，
REM pip 会报 "Missing dependencies for SOCKS support"。
REM 本脚本访问的是可直连的 PyPI 镜像，故临时清除代理变量。
REM (setlocal/endlocal 作用域内，不影响脚本结束后其他程序。)
set "ALL_PROXY="
set "HTTP_PROXY="
set "HTTPS_PROXY="
set "http_proxy="
set "https_proxy="

REM ===================================================================
REM  LLC 增益曲线 —— 一键构建脚本
REM
REM  完成：定位工程目录 -> 检查/创建 .venv -> 安装依赖 -> 运行 pytest
REM        -> 清理旧 build/dist -> onedir 构建 -> onefile 构建
REM        -> 校验 EXE -> 输出 SHA-256
REM
REM  任何一步失败都会以非零退出码结束。
REM  全部路径均加引号，兼容中文路径与空格。
REM ===================================================================

REM ---- 1. 定位脚本自身所在的工程根目录（不依赖当前工作目录） ----
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJ=%%~fI"
echo ============================================================
echo  工程根目录: "%PROJ%"
echo ============================================================
cd /d "%PROJ%" || (echo [错误] 无法进入工程目录 & exit /b 1)

set "VENV=%PROJ%\.venv"
set "VPY=%VENV%\Scripts\python.exe"
set "SPEC=%PROJ%\LLC_Gain_Curve.spec"
set "EXE=%PROJ%\dist\LLC增益曲线.exe"
set "WHEELS=%PROJ%\offline_wheels"

REM ---- 2. 查找可用的宿主 Python (3.10 ~ 3.12, 64 位) ----
if exist "%VPY%" goto :venv_ready

set "HOSTPY="
REM 候选检查：除了能运行，还必须带完整的 venv（能创建虚拟环境）。
REM 便携版 / 精简版 Python 可能缺失 venv 子模块，直接跳过。
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
    echo [错误] 未找到 64 位 Python 3.10 - 3.12。
    echo        请先安装，例如: winget install -e --id Python.Python.3.11
    exit /b 2
)
echo [1/8] 使用宿主 Python: !HOSTPY!

echo [2/8] 创建虚拟环境 "%VENV%"
!HOSTPY! -m venv "%VENV%" || (echo [错误] 创建虚拟环境失败 & exit /b 3)

:venv_ready
if not exist "%VPY%" (echo [错误] 虚拟环境异常，缺少 "%VPY%" & exit /b 3)
echo [2/8] 虚拟环境就绪
"%VPY%" -c "import sys;print('       Python',sys.version.split()[0],'64bit' if sys.maxsize>2**32 else '32bit')"

REM ---- 3. 安装依赖（优先离线 wheels，其次在线） ----
echo [3/8] 安装依赖...
"%VPY%" -m pip install --quiet --upgrade pip >nul 2>&1
if exist "%WHEELS%\*.whl" (
    echo        检测到离线 wheel 目录，优先离线安装
    "%VPY%" -m pip install --quiet --no-index --find-links "%WHEELS%" -r "%PROJ%\requirements.txt"
    if !errorlevel! neq 0 (
        echo        离线安装失败，改为在线安装
        "%VPY%" -m pip install --quiet -r "%PROJ%\requirements.txt" || (echo [错误] 依赖安装失败 & exit /b 4)
    )
) else (
    "%VPY%" -m pip install --quiet -r "%PROJ%\requirements.txt" || (echo [错误] 依赖安装失败 & exit /b 4)
)
echo        依赖版本清单:
"%VPY%" -m pip list --format=columns 2>nul | findstr /I "numpy matplotlib PySide6 pyinstaller pytest"

REM ---- 4. 运行测试，失败即停止 ----
echo [4/8] 运行 pytest ...
set "QT_QPA_PLATFORM=offscreen"
"%VPY%" -m pytest "%PROJ%\tests" -q
if !errorlevel! neq 0 (
    echo [错误] 单元测试未通过，已中止构建。
    exit /b 5
)
set "QT_QPA_PLATFORM="
echo        测试全部通过

REM ---- 5. 清理旧的构建产物与缓存 ----
echo [5/8] 清理旧 build / dist / 缓存 ...
if exist "%PROJ%\build" rmdir /s /q "%PROJ%\build"
if exist "%PROJ%\dist"  rmdir /s /q "%PROJ%\dist"
for /d /r "%PROJ%" %%D in (__pycache__) do if exist "%%D" rmdir /s /q "%%D" 2>nul
if exist "%PROJ%\.pytest_cache" rmdir /s /q "%PROJ%\.pytest_cache"

REM ---- 6. 先构建 onedir 版本并验证 ----
echo [6/8] 构建 onedir 版本 ...
set "LLC_BUILD_MODE=onedir"
"%VPY%" -m PyInstaller --clean --noconfirm "%SPEC%"
if !errorlevel! neq 0 (echo [错误] onedir 构建失败 & exit /b 6)

set "ONEDIR_EXE=%PROJ%\dist\LLC增益曲线_onedir\LLC增益曲线.exe"
if not exist "%ONEDIR_EXE%" (echo [错误] 未生成 onedir EXE & exit /b 6)
echo        onedir 构建成功: "%ONEDIR_EXE%"

echo        启动 onedir 版本进行验证 (8 秒) ...
start "" "%ONEDIR_EXE%"
timeout /t 8 /nobreak >nul
tasklist /FI "IMAGENAME eq LLC增益曲线.exe" 2>nul | find /I "LLC增益曲线.exe" >nul
if !errorlevel! neq 0 (
    echo [错误] onedir 版本启动后进程不存在，构建中止。
    exit /b 7
)
echo        onedir 版本启动正常，关闭该进程
taskkill /IM "LLC增益曲线.exe" /F >nul 2>&1
timeout /t 2 /nobreak >nul

REM ---- 7. 构建最终 onefile 版本 ----
echo [7/8] 构建 onefile 单文件 EXE ...
set "LLC_BUILD_MODE=onefile"
if exist "%PROJ%\build" rmdir /s /q "%PROJ%\build"
"%VPY%" -m PyInstaller --clean --noconfirm "%SPEC%"
if !errorlevel! neq 0 (echo [错误] onefile 构建失败 & exit /b 8)
if not exist "%EXE%" (echo [错误] 未生成 "%EXE%" & exit /b 8)

REM ---- 8. 验证最终 EXE：启动 -> 存活 -> 退出 -> 再启动 ----
echo [8/8] 验证最终 EXE ...
for %%F in ("%EXE%") do set "EXESIZE=%%~zF"
if "!EXESIZE!"=="0" (echo [错误] EXE 大小为 0 & exit /b 9)

echo        第一次启动 (首次运行需解压，等待 20 秒) ...
start "" "%EXE%"
timeout /t 20 /nobreak >nul
tasklist /FI "IMAGENAME eq LLC增益曲线.exe" 2>nul | find /I "LLC增益曲线.exe" >nul
if !errorlevel! neq 0 (
    echo [错误] 最终 EXE 启动失败，进程不存在。
    echo        请运行 scripts\build_debug_console.bat 获取详细错误。
    exit /b 10
)
echo        进程存活，正常。关闭 ...
taskkill /IM "LLC增益曲线.exe" /F >nul 2>&1
timeout /t 3 /nobreak >nul
tasklist /FI "IMAGENAME eq LLC增益曲线.exe" 2>nul | find /I "LLC增益曲线.exe" >nul
if !errorlevel! equ 0 (
    echo [警告] 关闭后仍有残留进程
) else (
    echo        进程已正常退出
)

echo        第二次启动，验证可重复运行 ...
start "" "%EXE%"
timeout /t 15 /nobreak >nul
tasklist /FI "IMAGENAME eq LLC增益曲线.exe" 2>nul | find /I "LLC增益曲线.exe" >nul
if !errorlevel! neq 0 (echo [错误] 第二次启动失败 & exit /b 11)
echo        第二次启动成功
taskkill /IM "LLC增益曲线.exe" /F >nul 2>&1

REM ---- 输出结果与 SHA-256 ----
echo.
echo ============================================================
echo  构建成功
echo ============================================================
echo  EXE 路径 : "%EXE%"
echo  文件大小 : !EXESIZE! 字节
REM certutil 输出中，哈希值是唯一一行"纯十六进制(可能含空格)"的内容。
REM 这里要求该行以十六进制字符开头，避免匹配到空行；
REM 不能使用 skip=1，否则会跳过哈希行本身。
set "SHA="
for /f "tokens=* delims=" %%H in ('certutil -hashfile "%EXE%" SHA256 ^| findstr /R /C:"^[0-9a-fA-F][0-9a-fA-F ]*$"') do (
    if not defined SHA set "SHA=%%H"
)
if defined SHA (
    set "SHA=!SHA: =!"
    echo  SHA-256  : !SHA!
) else (
    echo  SHA-256  : [获取失败，可手动执行 certutil -hashfile "%EXE%" SHA256]
)
echo ============================================================
endlocal
exit /b 0
