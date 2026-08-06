# -*- coding: utf-8 -*-
"""中文字体自动选择与 Matplotlib 全局样式配置。

设计要点
--------
1. 只使用目标系统 **已安装** 的字体，不携带任何外部字体文件作为运行依赖。
2. 按优先级探测常见 Windows 中文字体，找不到则逐级回退，
   最终回退到 Matplotlib 内置 DejaVu Sans（此时中文可能显示为方框，
   但程序不会崩溃，并会在日志中给出提示）。
3. 修正 ``axes.unicode_minus``，保证负号正常显示。
"""

from __future__ import annotations

import sys

import matplotlib
from matplotlib import font_manager

#: 中文字体优先级列表。前面的优先，覆盖 Windows 10/11 常见情况。
PREFERRED_CJK_FONTS: tuple[str, ...] = (
    "Microsoft YaHei UI",
    "Microsoft YaHei",
    "微软雅黑",
    "SimHei",
    "黑体",
    "Microsoft JhengHei",
    "SimSun",
    "宋体",
    "NSimSun",
    "FangSong",
    "KaiTi",
    "DengXian",
    "等线",
    # Linux / 其他平台上的常见回退（便于开发期自测）
    "Noto Sans CJK SC",
    "Noto Sans CJK JP",
    "Source Han Sans SC",
    "WenQuanYi Zen Hei",
    "WenQuanYi Micro Hei",
    "Droid Sans Fallback",
    "AR PL UMing CN",
)


def _installed_font_names() -> set[str]:
    """返回当前系统上 Matplotlib 能识别的全部字体名集合。"""
    names: set[str] = set()
    for font in font_manager.fontManager.ttflist:
        try:
            names.add(font.name)
        except Exception:  # pragma: no cover - 个别损坏字体文件
            continue
    return names


def pick_cjk_font() -> tuple[str | None, list[str]]:
    """挑选一个可用的中文字体。

    返回
    ----
    ``(chosen_font_or_None, ordered_family_list)``

    ``ordered_family_list`` 可直接赋给 ``rcParams['font.sans-serif']``，
    其中把命中的字体放在最前，后面保留其他候选与 DejaVu Sans 兜底。
    """
    installed = _installed_font_names()

    chosen: str | None = None
    for name in PREFERRED_CJK_FONTS:
        if name in installed:
            chosen = name
            break

    family: list[str] = []
    if chosen is not None:
        family.append(chosen)
    # 其余候选也一并写入，交给 Matplotlib 逐级回退
    family.extend(n for n in PREFERRED_CJK_FONTS if n != chosen)
    family.append("DejaVu Sans")
    return chosen, family


def configure_matplotlib_chinese(verbose: bool = False) -> str | None:
    """配置 Matplotlib 使用中文字体，并修正负号显示。

    返回实际选中的字体名；若系统无任何中文字体则返回 ``None``。
    """
    chosen, family = pick_cjk_font()

    matplotlib.rcParams["font.sans-serif"] = family
    matplotlib.rcParams["font.family"] = "sans-serif"
    # 关键：使用 ASCII 连字符，避免中文字体缺少 U+2212 导致负号变方框
    matplotlib.rcParams["axes.unicode_minus"] = False

    if verbose:
        if chosen:
            print(f"[字体] 已选用中文字体：{chosen}", file=sys.stderr)
        else:
            print(
                "[字体] 警告：未在系统中找到可用的中文字体，"
                "中文可能显示为方框。程序仍可正常运行。",
                file=sys.stderr,
            )
    return chosen


def qt_font_family() -> str:
    """返回适合 Qt 控件使用的字体名（找不到中文字体时返回空串）。"""
    chosen, _ = pick_cjk_font()
    return chosen or ""
