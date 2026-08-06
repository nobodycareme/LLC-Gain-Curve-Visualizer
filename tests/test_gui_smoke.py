# -*- coding: utf-8 -*-
"""GUI 冒烟测试（离屏运行，无需真实显示器）。

符号体系：K = Lm/Lr，fn = fs/fr。

本测试用 ``QT_QPA_PLATFORM=offscreen`` 启动真实的 PySide6 窗口，
覆盖：
* 程序能构造主窗口且无异常；
* 默认曲线数据正常（9 条参考曲线 + 1 条当前 Q 粗线）；
* 图例包含四种特征点标记（fnp / fnr=1 / 峰值 / 工作点 fn）；
* **反复拖动 K / Q / fn 后，Matplotlib 图形对象数量不增长**；
* fr 与纵轴上限可修改且生效；
* 非法/极端输入不会导致崩溃；
* 界面文字与结果区非旧符号（无 Ln = Lm/Lr、无 K = fs/fr）。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MPLBACKEND", "Agg")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 冒烟测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_model import Q_FAMILY  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    w = app_main.MainWindow()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _artist_census(win) -> dict:
    """统计坐标轴上的图形对象数量（复用 GainPlot 的实现）。"""
    return win.plot.artist_census()


# ---------------------------------------------------------------------------
# 启动与默认状态
# ---------------------------------------------------------------------------
def test_window_constructs(win):
    assert win.windowTitle() == app_main.APP_TITLE
    assert win.canvas is not None


def test_default_curves_present(win):
    """9 条参考曲线 + 1 条当前 Q 曲线 + 3 条竖线 + 4 个标记 = 17 条 line。"""
    assert len(win.plot.hFamily) == len(Q_FAMILY) == 9
    assert len(win.ax.lines) == 17


def test_default_curve_data_is_finite(win):
    import numpy as np
    y = win.plot.hCurrent.get_ydata()
    assert len(y) == 3000
    assert np.all(np.isfinite(y))
    for line in win.plot.hFamily:
        assert np.all(np.isfinite(line.get_ydata()))


def test_axes_configuration(win):
    assert win.ax.get_xscale() == "log"
    assert win.ax.get_xlim() == pytest.approx((0.1, 10.0))
    assert win.ax.get_ylim()[0] == pytest.approx(0.0)
    assert win.ax.get_ylim()[1] == pytest.approx(2.2)
    assert "归一化频率 fn" in win.ax.get_xlabel()


# ---------------------------------------------------------------------------
# 图例必须区分四种标记
# ---------------------------------------------------------------------------
def test_legend_contains_four_markers(win):
    labels = [t.get_text() for t in win.plot.legend.get_texts()]
    joined = " | ".join(labels)
    assert "fnp" in joined
    assert "fnr=1" in joined
    assert "峰值" in joined
    assert "工作点 fn" in joined
    # 9 条参考 Q + 当前 Q + 4 个标记
    assert len(labels) == 14


def test_legend_shows_current_q_value(win):
    labels = [t.get_text() for t in win.plot.legend.get_texts()]
    assert any(lbl.startswith("当前 Q 曲线：Q=") for lbl in labels)


def test_markers_have_distinct_shapes(win):
    shapes = {
        win.plot.hFnpPoint.get_marker(),
        win.plot.hFnrPoint.get_marker(),
        win.plot.hPeakPoint.get_marker(),
        win.plot.hWorkPoint.get_marker(),
    }
    assert len(shapes) == 4, "四种特征点必须使用不同的标记图案"


# ---------------------------------------------------------------------------
# 关键回归：拖动不产生新对象
# ---------------------------------------------------------------------------
def test_no_artist_growth_on_heavy_dragging(win):
    """模拟长时间连续拖动 K/Q/fn，图形对象数量必须保持恒定。"""
    before = _artist_census(win)

    for step in range(0, 1001, 25):
        win.sliderK.setValue(step)
        win._do_update()
        win.sliderQ.setValue(1000 - step)
        win._do_update()
        win.sliderFn.setValue((step * 7) % 1001)
        win._do_update()

    after = _artist_census(win)
    assert after == before, f"拖动后图形对象数量发生变化：{before} -> {after}"


def test_no_artist_growth_on_fr_and_ymax_changes(win):
    before = _artist_census(win)
    for fr in (50.0, 124.4, 300.0, 1000.0):
        win.editFr.setValue(fr)
        win._do_update()
    for ym in (0.5, 2.2, 10.0, 50.0):
        win.editYmax.setValue(ym)
        win._do_update()
    assert _artist_census(win) == before


def test_vertical_lines_are_reused_not_recreated(win):
    """三条竖线必须是同一批对象（id 不变），只更新位置。"""
    ids_before = (id(win.plot.hFnpLine), id(win.plot.hFnrLine), id(win.plot.hWorkLine))
    for step in (0, 250, 500, 750, 1000):
        win.sliderK.setValue(step)
        win._do_update()
    ids_after = (id(win.plot.hFnpLine), id(win.plot.hFnrLine), id(win.plot.hWorkLine))
    assert ids_before == ids_after


# ---------------------------------------------------------------------------
# 交互逻辑正确性
# ---------------------------------------------------------------------------
def test_k_change_updates_all_family_curves(win):
    """K = Lm/Lr 改变后所有参考 Q 曲线都应更新。"""
    import numpy as np
    win.sliderK.setValue(0)      # K = 1.5
    win._do_update()
    snap = [line.get_ydata().copy() for line in win.plot.hFamily]

    win.sliderK.setValue(1000)   # K = 10
    win._do_update()
    for old, line in zip(snap, win.plot.hFamily):
        assert not np.allclose(old, line.get_ydata()), \
            "K 改变后所有参考 Q 曲线都应更新"


def test_fn_change_does_not_alter_curve_shape(win):
    """工作点 fn 只移动工作点，不能改变任何曲线的形状。"""
    import numpy as np
    win.sliderFn.setValue(200)
    win._do_update()
    cur = win.plot.hCurrent.get_ydata().copy()
    fam = [l.get_ydata().copy() for l in win.plot.hFamily]

    win.sliderFn.setValue(900)
    win._do_update()
    assert np.allclose(cur, win.plot.hCurrent.get_ydata())
    for old, line in zip(fam, win.plot.hFamily):
        assert np.allclose(old, line.get_ydata())


def test_work_point_lies_on_current_curve(win):
    """工作点必须落在当前黑色 Q 曲线上。"""
    import numpy as np
    from llc_model import llc_gain
    for step in (100, 400, 700, 950):
        win.sliderFn.setValue(step)
        win._do_update()
        K = app_main._lin_from_slider(win.sliderK.value(), 1.5, 10.0)
        Q = app_main._log_from_slider(win.sliderQ.value(), 0.05, 10.0)
        xd = win.plot.hWorkPoint.get_xdata()
        yd = win.plot.hWorkPoint.get_ydata()
        assert len(xd) == 1
        expected = float(llc_gain(float(xd[0]), K, Q))
        assert float(yd[0]) == pytest.approx(expected, rel=1e-9)


def test_fr_only_affects_real_frequency_not_shape(win):
    import numpy as np
    win.editFr.setValue(124.4)
    win._do_update()
    shape = win.plot.hCurrent.get_ydata().copy()

    win.editFr.setValue(500.0)
    win._do_update()
    assert np.allclose(shape, win.plot.hCurrent.get_ydata()), \
        "修改 fr 不应改变归一化增益曲线形状"
    assert "500.000 kHz" in win.resultBox.toPlainText()


def test_ymax_applies_to_axis(win):
    win.editYmax.setValue(7.5)
    win._do_update()
    assert win.ax.get_ylim()[1] == pytest.approx(7.5)


def test_result_box_contains_required_fields(win):
    win._do_update()
    text = win.resultBox.toPlainText()
    for token in ("K    =", "Q    =", "fn   =", "M(fn)=", "fs", "fnp",
                  "fp", "M(fnp)", "fnr", "fr", "M(fnr)", "fn_peak",
                  "f_peak", "M_peak", "彩色细线", "黑色粗线", "并联谐振",
                  "串联谐振", "K  = Lm / Lr", "fn = fs / fr"):
        assert token in text, f"结果区缺少字段：{token}"


def test_result_box_has_no_old_symbols(win):
    """结果区不得出现旧的 Ln = Lm/Lr 或 K = fs/fr。"""
    win._do_update()
    text = win.resultBox.toPlainText()
    assert "Ln" not in text
    assert "K  = fs / fr" not in text


def test_fnp_line_tracks_K(win):
    import math
    from llc_model import fn_parallel
    for step in (0, 500, 1000):
        win.sliderK.setValue(step)
        win._do_update()
        K = app_main._lin_from_slider(step, 1.5, 10.0)
        xd = win.plot.hFnpLine.get_xdata()
        assert float(xd[0]) == pytest.approx(fn_parallel(K))


def test_fnr_line_stays_at_one(win):
    for step in (0, 300, 800, 1000):
        win.sliderK.setValue(step)
        win._do_update()
        assert float(win.plot.hFnrLine.get_xdata()[0]) == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 交互性能：K 只更新整条曲线；Q 只更新当前曲线；fn 只移动工作点
# ---------------------------------------------------------------------------
def test_k_change_computes_family_and_current(win):
    win.plot.stats["family"] = 0
    win.sliderK.setValue(400)
    win._do_update()
    assert win.plot.stats["family"] == 1, "K 改变应重算固定参考曲线族"


def test_q_change_does_not_recompute_family(win):
    win.plot.stats["family"] = 0
    win.sliderQ.setValue(400)
    win._do_update()
    assert win.plot.stats["family"] == 0, "Q 改变不应重算固定曲线族"


def test_fn_change_recomputes_nothing(win):
    win.plot.stats["family"] = 0
    win.plot.stats["current"] = 0
    win.plot.stats["peak"] = 0
    win.sliderFn.setValue(400)
    win._do_update()
    assert win.plot.stats["family"] == 0
    assert win.plot.stats["current"] == 0
    assert win.plot.stats["peak"] == 0


# ---------------------------------------------------------------------------
# 健壮性
# ---------------------------------------------------------------------------
def test_extreme_parameters_do_not_crash(win):
    for k in (0, 1000):
        for q in (0, 1000):
            for fn in (0, 1000):
                win.sliderK.setValue(k)
                win.sliderQ.setValue(q)
                win.sliderFn.setValue(fn)
                win._do_update()
    assert win.resultBox.toPlainText() != ""


def test_reentrancy_guard(win):
    """重入时应记录 pending 而不是递归执行。"""
    win._updating = True
    win._pending = False
    win._do_update()
    assert win._pending is True
    win._updating = False
    win._pending = False


def test_canvas_renders_without_exception(win):
    """真实渲染一次，确保字体/标记/图例都能画出来。"""
    win._do_update()
    win.canvas.draw()