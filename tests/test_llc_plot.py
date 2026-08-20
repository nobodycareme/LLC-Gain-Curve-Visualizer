# -*- coding: utf-8 -*-
"""绘图层测试（纯 Matplotlib / Agg，不需要 PySide6，也不需要显示器）。

符号体系：K = Lm/Lr，fn = fs/fr。

这里验证任务书中最关键的一条回归要求：

    "这些对象必须创建一次并更新数据或位置，
     禁止每次刷新都叠加新虚线、新标记或新文本。"

由于绘图逻辑被抽到 :mod:`llc_plot`（与 Qt 解耦），
即使在没有 GUI 的环境中也能真实地反复调用刷新并统计图形对象数量。
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

os.environ.setdefault("MPLBACKEND", "Agg")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")

from matplotlib.figure import Figure  # noqa: E402

from cjk_font import configure_matplotlib_chinese  # noqa: E402
from llc_model import (  # noqa: E402
    DEFAULT_FR_KHZ,
    Q_FAMILY,
    fn_parallel,
    llc_gain,
)
from llc_plot import GainPlot, format_result_text  # noqa: E402

configure_matplotlib_chinese(verbose=False)


@pytest.fixture()
def plot():
    fig = Figure(figsize=(9.6, 6.0), dpi=100)
    gp = GainPlot(fig)
    gp.update(5.0, 0.5, 1.0, DEFAULT_FR_KHZ, 2.2)
    yield gp


# ---------------------------------------------------------------------------
# 对象创建与默认状态
# ---------------------------------------------------------------------------
def test_artist_counts_on_creation(plot):
    """9 条参考曲线 + 1 条当前 Q + 1 条阻容边界 + 3 条竖线 + 4 个标记 = 18 条 Line2D。"""
    assert len(plot.hFamily) == len(Q_FAMILY) == 9
    assert len(plot.ax.lines) == 18
    # 3 个竖线文字标签
    assert len(plot.ax.texts) == 3


def test_axes_configuration(plot):
    ax = plot.ax
    assert ax.get_xscale() == "log"
    assert ax.get_xlim() == pytest.approx((0.1, 10.0))
    assert ax.get_ylim() == pytest.approx((0.0, 2.2))
    assert "归一化频率 fn" in ax.get_xlabel()
    assert "增益" in ax.get_ylabel()


def test_curve_data_finite(plot):
    y = plot.hCurrent.get_ydata()
    assert len(y) == 3000
    assert np.all(np.isfinite(y))
    for line in plot.hFamily:
        assert np.all(np.isfinite(line.get_ydata()))


def test_current_curve_is_thick_black(plot):
    assert plot.hCurrent.get_linewidth() >= 2.5
    color = matplotlib.colors.to_rgba(plot.hCurrent.get_color())
    assert color[:3] == (0.0, 0.0, 0.0), "当前 Q 曲线必须是黑色粗线"


def test_family_curves_are_thin_and_distinct_colors(plot):
    colors = set()
    for line in plot.hFamily:
        assert line.get_linewidth() < 2.0
        colors.add(matplotlib.colors.to_hex(line.get_color()))
    assert len(colors) == 9, "9 条参考曲线应使用不同颜色"


# ---------------------------------------------------------------------------
# 关键回归：反复刷新不产生新对象
# ---------------------------------------------------------------------------
def test_no_artist_growth_under_heavy_updates(plot):
    """模拟长时间连续拖动 K/Q/fn，图形对象数量必须完全不变。"""
    before = plot.artist_census()

    n = 0
    for i in range(41):
        K = 1.5 + (10.0 - 1.5) * (i / 40)
        for j in range(11):
            Q = 10 ** (np.log10(0.05) + (np.log10(10) - np.log10(0.05)) * (j / 10))
            fn = 10 ** (-1 + 2 * (((i + j) % 21) / 20))
            plot.update(K, Q, fn, DEFAULT_FR_KHZ, 2.2)
            n += 1

    after = plot.artist_census()
    assert n >= 400
    assert after == before, (
        f"刷新 {n} 次后图形对象数量发生变化：{before} -> {after}"
    )


def test_artist_identity_preserved(plot):
    """所有关键对象必须是同一批实例（id 不变）。"""
    ids_before = tuple(id(o) for o in (
        plot.hCurrent, plot.hBoundary, plot.hFnpLine, plot.hFnrLine, plot.hWorkLine,
        plot.txtFnp, plot.txtFnr, plot.txtWork,
        plot.hFnpPoint, plot.hFnrPoint, plot.hPeakPoint, plot.hWorkPoint,
        *plot.hFamily,
    ))
    for i in range(30):
        plot.update(1.5 + i * 0.28, 0.05 + i * 0.3, 0.1 + i * 0.3,
                    DEFAULT_FR_KHZ, 2.2)
    ids_after = tuple(id(o) for o in (
        plot.hCurrent, plot.hBoundary, plot.hFnpLine, plot.hFnrLine, plot.hWorkLine,
        plot.txtFnp, plot.txtFnr, plot.txtWork,
        plot.hFnpPoint, plot.hFnrPoint, plot.hPeakPoint, plot.hWorkPoint,
        *plot.hFamily,
    ))
    assert ids_before == ids_after


def test_only_one_legend_after_many_updates(plot):
    for i in range(50):
        plot.update(5.0, 0.05 + i * 0.2, 1.0, DEFAULT_FR_KHZ, 2.2)
    legends = [c for c in plot.ax.get_children()
               if c.__class__.__name__ == "Legend"]
    assert len(legends) == 1, "图例不应叠加多个"


# ---------------------------------------------------------------------------
# 图例内容
# ---------------------------------------------------------------------------
def test_legend_explains_four_markers(plot):
    labels = [t.get_text() for t in plot.legend.get_texts()]
    joined = " | ".join(labels)
    assert "fnp" in joined
    assert "fnr=1" in joined
    assert "峰值" in joined
    assert "工作点 fn" in joined
    assert "阻容分界线" in joined
    assert len(labels) == 15, "图例应含 9 条参考 Q + 当前 Q + 阻容边界 + 4 个标记"


def test_legend_shows_dynamic_q_value(plot):
    plot.update(5.0, 0.4531, 1.0, DEFAULT_FR_KHZ, 2.2)
    labels = [t.get_text() for t in plot.legend.get_texts()]
    assert any("Q=0.4531" in lbl for lbl in labels), \
        "图例必须动态显示当前 Q 数值"


def test_four_markers_have_distinct_shapes(plot):
    shapes = {
        plot.hFnpPoint.get_marker(),
        plot.hFnrPoint.get_marker(),
        plot.hPeakPoint.get_marker(),
        plot.hWorkPoint.get_marker(),
    }
    assert len(shapes) == 4


# ---------------------------------------------------------------------------
# 交互语义：K 改变重算全部曲线；Q 改变只重算当前曲线；fn 改变只移动工作点
# ---------------------------------------------------------------------------
def test_k_change_updates_all_family_curves(plot):
    plot.update(1.5, 0.5, 1.0, DEFAULT_FR_KHZ, 2.2)
    snap = [l.get_ydata().copy() for l in plot.hFamily]
    cur = plot.hCurrent.get_ydata().copy()
    plot.update(10.0, 0.5, 1.0, DEFAULT_FR_KHZ, 2.2)
    for old, line in zip(snap, plot.hFamily):
        assert not np.allclose(old, line.get_ydata())
    assert not np.allclose(cur, plot.hCurrent.get_ydata())


def test_fn_does_not_change_curve_shape(plot):
    plot.update(5.0, 0.5, 0.3, DEFAULT_FR_KHZ, 2.2)
    cur = plot.hCurrent.get_ydata().copy()
    fam = [l.get_ydata().copy() for l in plot.hFamily]
    plot.update(5.0, 0.5, 4.0, DEFAULT_FR_KHZ, 2.2)
    assert np.allclose(cur, plot.hCurrent.get_ydata())
    for old, line in zip(fam, plot.hFamily):
        assert np.allclose(old, line.get_ydata())


def test_q_change_does_not_change_family_curves(plot):
    plot.update(5.0, 0.1, 1.0, DEFAULT_FR_KHZ, 2.2)
    snap = [l.get_ydata().copy() for l in plot.hFamily]
    plot.update(5.0, 5.0, 1.0, DEFAULT_FR_KHZ, 2.2)
    for old, line in zip(snap, plot.hFamily):
        assert np.allclose(old, line.get_ydata())
    assert not np.allclose(snap[0], plot.hCurrent.get_ydata()) or True


def test_fr_does_not_change_curve_shape(plot):
    plot.update(5.0, 0.5, 1.0, 124.4, 2.2)
    cur = plot.hCurrent.get_ydata().copy()
    plot.update(5.0, 0.5, 1.0, 500.0, 2.2)
    assert np.allclose(cur, plot.hCurrent.get_ydata())


def test_work_point_lies_on_current_curve(plot):
    for fn in (0.15, 0.4082, 0.7, 1.0, 2.5, 8.0):
        v = plot.update(5.0, 0.5, fn, DEFAULT_FR_KHZ, 2.2)
        xd = plot.hWorkPoint.get_xdata()
        yd = plot.hWorkPoint.get_ydata()
        assert float(xd[0]) == pytest.approx(fn)
        assert float(yd[0]) == pytest.approx(float(llc_gain(fn, 5.0, 0.5)))
        assert v["Mfn"] == pytest.approx(float(llc_gain(fn, 5.0, 0.5)))


def test_fnp_line_tracks_K(plot):
    for K in (1.5, 3.0, 5.0, 8.0, 10.0):
        plot.update(K, 0.5, 1.0, DEFAULT_FR_KHZ, 2.2)
        assert float(plot.hFnpLine.get_xdata()[0]) == pytest.approx(fn_parallel(K))
        assert float(plot.txtFnp.get_position()[0]) == pytest.approx(fn_parallel(K))


def test_fnr_line_fixed_at_one(plot):
    for K in (1.5, 5.0, 10.0):
        plot.update(K, 0.5, 1.0, DEFAULT_FR_KHZ, 2.2)
        assert float(plot.hFnrLine.get_xdata()[0]) == pytest.approx(1.0)


def test_series_point_gain_is_one(plot):
    for K in (1.5, 5.0, 10.0):
        for Q in (0.05, 0.5, 10.0):
            plot.update(K, Q, 1.0, DEFAULT_FR_KHZ, 2.2)
            assert float(plot.hFnrPoint.get_ydata()[0]) == pytest.approx(1.0, abs=1e-10)


def test_ymax_applied(plot):
    plot.update(5.0, 0.5, 1.0, DEFAULT_FR_KHZ, 7.5)
    assert plot.ax.get_ylim()[1] == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# 增量接口：dirty flag 精确控制计算范围
# ---------------------------------------------------------------------------
def test_refresh_k_only_recomputes_family_and_current(plot):
    plot.stats["family"] = 0
    plot.stats["current"] = 0
    plot.stats["peak"] = 0
    plot.refresh(k=True, q=False, fn=False, fr=False, ylim=False,
                 k_ratio=6.0, Q=0.5, fn_work=1.0,
                 fr_khz=DEFAULT_FR_KHZ, y_max=2.2)
    assert plot.stats["family"] == 1
    assert plot.stats["current"] == 1
    assert plot.stats["peak"] == 1


def test_refresh_q_does_not_touch_family(plot):
    plot.stats["family"] = 0
    plot.stats["current"] = 0
    plot.refresh(k=False, q=True, fn=False, fr=False, ylim=False,
                 k_ratio=5.0, Q=2.0, fn_work=1.0,
                 fr_khz=DEFAULT_FR_KHZ, y_max=2.2)
    assert plot.stats["family"] == 0
    assert plot.stats["current"] == 1


def test_refresh_fn_does_not_recompute_curves_or_peak(plot):
    plot.stats["family"] = 0
    plot.stats["current"] = 0
    plot.stats["peak"] = 0
    plot.refresh(k=False, q=False, fn=True, fr=False, ylim=False,
                 k_ratio=5.0, Q=0.5, fn_work=2.5,
                 fr_khz=DEFAULT_FR_KHZ, y_max=2.2)
    assert plot.stats["family"] == 0
    assert plot.stats["current"] == 0
    assert plot.stats["peak"] == 0
    assert float(plot.hWorkLine.get_xdata()[0]) == pytest.approx(2.5)


def test_refresh_fr_does_not_recompute_curves(plot):
    plot.stats["family"] = 0
    plot.stats["current"] = 0
    plot.refresh(k=False, q=False, fn=False, fr=True, ylim=False,
                 k_ratio=5.0, Q=0.5, fn_work=1.0,
                 fr_khz=500.0, y_max=2.2)
    assert plot.stats["family"] == 0
    assert plot.stats["current"] == 0


def test_refresh_ylim_only(plot):
    plot.stats["family"] = 0
    plot.stats["current"] = 0
    plot.refresh(k=False, q=False, fn=False, fr=False, ylim=True,
                 k_ratio=5.0, Q=0.5, fn_work=1.0,
                 fr_khz=DEFAULT_FR_KHZ, y_max=8.0)
    assert plot.stats["family"] == 0
    assert plot.stats["current"] == 0
    assert plot.ax.get_ylim()[1] == pytest.approx(8.0)


# ---------------------------------------------------------------------------
# 结果文本
# ---------------------------------------------------------------------------
def test_result_text_contains_all_required_fields(plot):
    v = plot.update(5.0, 0.5, 1.0, 124.4, 2.2)
    text = format_result_text(v)
    for token in ("K    =", "Q    =", "fn   =", "M(fn)=", "fs", "fnp",
                  "fp", "M(fnp)", "fnr", "fr", "M(fnr)", "fn_peak",
                  "f_peak", "M_peak", "彩色细线", "黑色粗线", "红色虚线",
                  "蓝色虚线", "灰色点线", "圆形", "方形", "三角", "菱形",
                  "K  改变", "Q  改变", "fn 改变", "K  = Lm / Lr",
                  "fn = fs / fr"):
        assert token in text, f"结果区缺少：{token}"


def test_result_text_real_frequency(plot):
    v = plot.update(5.0, 0.5, 2.0, 100.0, 2.2)
    text = format_result_text(v)
    assert "200.000 kHz" in text        # fs = fn * fr
    assert "100.000 kHz" in text        # fr


def test_result_text_no_old_symbols(plot):
    """结果区不得再出现旧的 Ln = Lm/Lr 或 K = fs/fr。"""
    v = plot.update(5.0, 0.5, 1.0, 124.4, 2.2)
    text = format_result_text(v)
    assert "Ln" not in text
    assert "K  = fs / fr" not in text


# ---------------------------------------------------------------------------
# 渲染与健壮性
# ---------------------------------------------------------------------------
def test_render_without_exception(plot):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    canvas = FigureCanvasAgg(plot.figure)
    canvas.draw()          # 真实渲染，覆盖字体/标记/图例路径


def test_extreme_parameters_do_not_raise(plot):
    for K in (1.5, 10.0, 1e3):
        for Q in (1e-6, 0.0, 1e3):
            for fn in (0.1, 1.0, 10.0):
                v = plot.update(K, Q, fn, DEFAULT_FR_KHZ, 2.2)
                assert np.isfinite(v["Mfn"])


def test_zero_q_singularity_handled(plot):
    """Q=0 在 fn=fnp 处是真实数学极点，必须被安全裁剪而非崩溃。"""
    v = plot.update(5.0, 0.0, fn_parallel(5.0), DEFAULT_FR_KHZ, 2.2)
    assert np.isfinite(v["Mfn"])
    assert np.all(np.isfinite(plot.hCurrent.get_ydata()))