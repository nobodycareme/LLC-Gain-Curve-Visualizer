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

# 定向剔除本程序运行完全不需要的 Qt 插件与库（需求 7 瘦身）。
# 依据：程序仅用 QtCore/QtGui/QtWidgets + QPainter 栅格绘制，
# 无网络 / 无 SVG / 无图片文件加载 / 无 QTranslator / 无 OpenGL。
# 每类都经"构建→启动→操作 GUI→导出 PNG→自动测试"验证。
# 注意：按目标路径（b[0]）定向剔除，不手工删 DLL，构建流程确定可复现。
_BIN_DROP = {
    # 网络：由 generic/qtuiotouchplugin.dll 传递拉入，程序从不使用
    "qt6network.dll",
    # SVG：无运行时 SVG 资源
    "qt6svg.dll",
    # generic 插件：触屏输入，桌面程序不需要，且其依赖 Qt6Network
    "qtuiotouchplugin.dll",
    # iconengines：SVG 图标引擎
    "qsvgicon.dll",
    # imageformats：程序不加载任何 JPEG/WebP/TIFF/GIF/ICO/ICNS/TGA/WBMP/SVG 图片，
    # PNG 编解码内置于 Qt6Gui.dll，导出截图无需任何 imageformat 插件
    "qjpeg.dll", "qwebp.dll", "qtiff.dll", "qgif.dll", "qicns.dll",
    "qico.dll", "qtga.dll", "qwbmp.dll", "qsvg.dll", "qdds.dll",
    # platforms：正式 Windows 发布只需 qwindows.dll；
    # qdirect2d/qminimal/qoffscreen 仅测试环境需要
    "qdirect2d.dll", "qminimal.dll", "qoffscreen.dll",
    # styles：Qt6Widgets 内置 Windows/Fusion 等样式，无需额外插件
    "qmodernwindowsstyle.dll",
    # Qt 软件 OpenGL 回退库：纯 QPainter 栅格绘制从不触发 OpenGL 上下文
    "opengl32sw.dll",
    "libEGL.dll",
    "libGLESv2.dll",
    "d3dcompiler_47.dll",
    # libcrypto-1_1.dll：由 Python 标准库 hashlib 链（importlib.metadata→email→
    # random→hashlib→_hashlib.pyd）静态分析拉入。random 实际使用内置 _sha512，
    # 冻结应用运行路径从不触发 hashlib（无网络/无加密/无文件哈希）。
    # 经"构建→启动→操作 GUI→导出 PNG→自动测试"验证后可安全剔除。
    "libcrypto-1_1.dll",
}


def _keep_binary(entry):
    return os.path.basename(entry[0]).lower() not in _BIN_DROP


a.binaries = [b for b in a.binaries if _keep_binary(b)]

# 剔除整套 Qt 多语言翻译（程序不使用 QTranslator，需求 7.2）。
# 96 个 .qm 全部为无关数据；若未来需要中文 Qt 内置文案，再单独补 zh_CN。
a.datas = [d for d in a.datas
           if "\\translations\\" not in d[0].replace("/", "\\")]

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