# -*- coding: utf-8 -*-
"""中文字体自动选择逻辑测试。

注意：本测试运行在任意平台上都应通过。在没有任何中文字体的环境
（例如精简的 Linux 容器）中，``pick_cjk_font`` 允许返回 ``None``，
但必须保证：

* 返回的字体族列表非空且以 ``DejaVu Sans`` 兜底；
* ``axes.unicode_minus`` 被设为 ``False``，保证负号正常显示；
* 不抛出异常（绝不能因为字体缺失导致程序崩溃）。
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("MPLBACKEND", "Agg")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from cjk_font import (  # noqa: E402
    PREFERRED_CJK_FONTS,
    configure_matplotlib_chinese,
    pick_cjk_font,
    qt_font_family,
)


def test_pick_font_does_not_raise():
    chosen, family = pick_cjk_font()
    assert isinstance(family, list) and family
    assert chosen is None or isinstance(chosen, str)


def test_family_list_has_dejavu_fallback():
    _, family = pick_cjk_font()
    assert family[-1] == "DejaVu Sans", "字体族列表必须以 DejaVu Sans 兜底"


def test_windows_fonts_have_priority():
    """微软雅黑系列必须排在候选列表最前面。"""
    assert PREFERRED_CJK_FONTS[0] == "Microsoft YaHei UI"
    assert "Microsoft YaHei" in PREFERRED_CJK_FONTS[:3]
    assert "SimHei" in PREFERRED_CJK_FONTS


def test_chosen_font_is_first_installed_candidate():
    """若命中字体，它必须排在返回列表首位。"""
    chosen, family = pick_cjk_font()
    if chosen is not None:
        assert family[0] == chosen


def test_configure_sets_unicode_minus_false():
    configure_matplotlib_chinese(verbose=False)
    assert matplotlib.rcParams["axes.unicode_minus"] is False, \
        "必须关闭 unicode_minus，否则负号可能显示为方框"


def test_configure_sets_sans_serif_family():
    configure_matplotlib_chinese(verbose=False)
    fam = matplotlib.rcParams["font.family"]
    assert fam == ["sans-serif"] or fam == "sans-serif"
    assert matplotlib.rcParams["font.sans-serif"], "font.sans-serif 不应为空"


def test_qt_font_family_returns_str():
    fam = qt_font_family()
    assert isinstance(fam, str)


def test_negative_number_renders():
    """渲染含负号的文本，确保不抛异常。"""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    configure_matplotlib_chinese(verbose=False)
    fig = Figure()
    ax = fig.add_subplot(111)
    ax.plot([-2, -1, 0, 1], [-1, 0, 1, 2])
    ax.set_title("负号测试 -1.5")
    FigureCanvasAgg(fig).draw()
