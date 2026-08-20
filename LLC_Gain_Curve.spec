# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置：LLC 增益曲线。

同时支持 onedir 与 onefile 两种模式，由环境变量 ``LLC_BUILD_MODE`` 控制：

    set LLC_BUILD_MODE=onedir    先构建文件夹版本（便于定位启动问题）
    set LLC_BUILD_MODE=onefile   构建最终单文件 EXE（默认）

构建命令示例：
    pyinstaller --clean --noconfirm "LLC_Gain_Curve.spec"

设计说明
--------
* 运行路径为 main -> plot_widget -> llc_py -> cjk_font(qt_font_family)。
  全链路为纯 Python + PySide6-Essentials，**不 import numpy/matplotlib**，
  因此不再收集二者的 data/hidden-import。
* 只排除与运行无关的大型组件（Qt 的重型模块 / 开发工具 / 其他 GUI 框架），
  不盲目堆叠 hidden-import。
* Qt 平台插件由 PyInstaller 的 PySide6 hook 自动收集。
"""

import os

BUILD_MODE = os.environ.get("LLC_BUILD_MODE", "onefile").strip().lower()
APP_NAME = "LLC增益曲线"

block_cipher = None

# 纯 Qt + 纯 Python 绘图，无 matplotlib data / numpy / scipy
datas = []
hiddenimports = []

# 明确排除与本程序无关的大型组件，显著减小 EXE 体积
excludes = [
    # 其他 GUI 工具包
    "tkinter", "PyQt5", "PyQt6", "PySide2", "wx",
    # 科学计算栈（运行路径不含 numpy / matplotlib，一并排除）
    "numpy", "matplotlib", "scipy", "pandas", "sympy",
    "IPython", "jupyter", "notebook",
    "pytest", "setuptools", "pip", "wheel",
    # PySide6 中未使用的重型模块
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtSerialPort", "PySide6.QtSpatialAudio",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtTextToSpeech", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    # 本程序仅用 QtCore/QtGui/QtWidgets，QtNetwork 为无关传递依赖，排除
    "PySide6.QtNetwork",
]

a = Analysis(
    ["src\\main.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# 剔除 Qt 软件 OpenGL 回退库。本程序纯 QPainter 栅格绘制，从不触发
# OpenGL 上下文，此 20MB 库为无关依赖。按文件名定向剔除（不手工删 DLL，
# 而是让构建流程确定地排除；若未来某平台需要，移除该过滤即可恢复）。
a.binaries = [b for b in a.binaries
              if os.path.basename(b[0]).lower() not in {
                  "opengl32sw.dll",
                  "libEGL.dll",
                  "libGLESv2.dll",
                  "d3dcompiler_47.dll",
              }]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

if BUILD_MODE == "onedir":
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,          # 无控制台窗口
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME + "_onedir",
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=APP_NAME,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,          # 无控制台窗口
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )