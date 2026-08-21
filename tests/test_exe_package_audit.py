# -*- coding: utf-8 -*-
"""EXE 打包审计测试（需求 7 瘦身 / 需求 11）。

检查正式发布目录（onedir 的 _internal）不包含运行不需要的依赖：

- 整套 Qt 多语言翻译（translations/*.qm）
- 多余 imageformats 插件（程序不加载 JPEG/WebP/TIFF/GIF/ICO/ICNS/TGA/WBMP/SVG）
- 多余 platforms（正式 Windows 发布只需 qwindows.dll）
- Qt6Network.dll / Qt6Svg.dll（无网络 / 无 SVG）
- qtuiotouchplugin.dll（generic 触屏插件，且依赖 Qt6Network）
- qsvgicon.dll（SVG 图标引擎）
- qmodernwindowsstyle.dll（Qt6Widgets 内置样式）
- libcrypto-1_1.dll（hashlib 静态链，运行路径从不触发）
- opengl32sw.dll / libEGL.dll / libGLESv2.dll / d3dcompiler_47.dll（软件 OpenGL）

若发布目录不存在（未执行打包），测试跳过。
"""

from __future__ import annotations

import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERNAL = os.path.join(PROJECT_ROOT, "dist", "LLC增益曲线_onedir", "_internal")


def _rel(p):
    return os.path.relpath(p, INTERNAL).replace("\\", "/")


def _all_files():
    if not os.path.isdir(INTERNAL):
        return []
    out = []
    for root, _dirs, files in os.walk(INTERNAL):
        for f in files:
            out.append(os.path.join(root, f))
    return out


pytestmark = pytest.mark.skipif(
    not os.path.isdir(INTERNAL),
    reason="未构建 onedir 发布目录，跳过打包审计",
)


def test_no_translations_qm():
    bad = [f for f in _all_files() if f.lower().endswith(".qm")]
    assert not bad, f"发布目录不应包含 Qt 翻译文件：{[_rel(b) for b in bad[:5]]}"


def test_no_unnecessary_imageformats():
    bad = [f for f in _all_files() if "imageformats" in f.replace("\\", "/")]
    assert not bad, f"发布目录不应包含 imageformats 插件：{[_rel(b) for b in bad]}"


def test_only_qwindows_platform():
    platforms = [f for f in _all_files() if "plugins/platforms" in f.replace("\\", "/")]
    names = [os.path.basename(p).lower() for p in platforms]
    assert names == ["qwindows.dll"], f"platforms 应只剩 qwindows.dll，实际：{names}"


def test_no_network_or_svg():
    bad = [f for f in _all_files()
           if os.path.basename(f).lower() in {
               "qt6network.dll", "qt6svg.dll", "qtuiotouchplugin.dll",
               "qsvgicon.dll", "qsvg.dll",
           }]
    assert not bad, f"发布目录不应包含网络/SVG 依赖：{[_rel(b) for b in bad]}"


def test_no_software_opengl():
    bad = [f for f in _all_files()
           if os.path.basename(f).lower() in {
               "opengl32sw.dll", "libegl.dll", "libglesv2.dll",
               "d3dcompiler_47.dll",
           }]
    assert not bad, f"发布目录不应包含软件 OpenGL 库：{[_rel(b) for b in bad]}"


def test_no_libcrypto():
    bad = [f for f in _all_files()
           if os.path.basename(f).lower().startswith("libcrypto")]
    assert not bad, f"发布目录不应包含 libcrypto：{[_rel(b) for b in bad]}"


def test_no_modern_windows_style():
    bad = [f for f in _all_files()
           if os.path.basename(f).lower() == "qmodernwindowsstyle.dll"]
    assert not bad, f"发布目录不应包含 qmodernwindowsstyle：{[_rel(b) for b in bad]}"


def test_core_qt_binaries_present():
    """核心运行依赖必须仍在，防止过度剔除把程序弄坏。"""
    names = {os.path.basename(f).lower() for f in _all_files()}
    for required in ("qt6core.dll", "qt6gui.dll", "qt6widgets.dll",
                     "qwindows.dll", "python310.dll", "pyside6.abi3.dll",
                     "shiboken6.abi3.dll"):
        assert required in names, f"缺少核心依赖：{required}"
