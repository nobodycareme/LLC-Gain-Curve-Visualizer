@echo off
chcp 65001 >nul 2>&1
setlocal EnableExtensions EnableDelayedExpansion

REM ===================================================================
REM  诊断用：构建【带控制台】的单文件 EXE，用于查看启动报错。
REM  注意：这不是最终交付版本，最终交付版本无控制台窗口。
REM  产物: dist\LLC增益曲线_debug.exe
REM ===================================================================

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJ=%%~fI"
cd /d "%PROJ%" || exit /b 1

set "VPY=%PROJ%\.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [错误] 未找到虚拟环境，请先运行 scripts\build_exe.bat
    exit /b 2
)

echo 构建带控制台的诊断版本 ...
"%VPY%" -m PyInstaller --clean --noconfirm --onefile --console ^
    --name "LLC增益曲线_debug" ^
    --paths "%PROJ%\src" ^
    --collect-data matplotlib ^
    --hidden-import matplotlib.backends.backend_qtagg ^
    --exclude-module tkinter --exclude-module scipy --exclude-module pandas ^
    --exclude-module PyQt5 --exclude-module PyQt6 --exclude-module PySide2 ^
    "%PROJ%\src\main.py"
if !errorlevel! neq 0 (echo [错误] 诊断版本构建失败 & exit /b 3)

echo.
echo 诊断 EXE: "%PROJ%\dist\LLC增益曲线_debug.exe"
echo 请在命令行中直接运行它，控制台会显示完整错误堆栈。
endlocal
exit /b 0
