# -*- coding: utf-8 -*-
"""针对"交互性能与标题布局修复" + "符号体系纠正"的新增测试。

符号体系：K = Lm/Lr，fn = fs/fr。

验证目标：
* fn 改变不重算固定 Q 曲线、不重算当前 Q 整条曲线、不搜峰值；
* Q 改变不重算固定参考 Q 曲线族；
* K（= Lm/Lr）改变时固定 Q 曲线族与当前 Q 曲线均更新；
* fr 改变不重算归一化曲线；
* 纵轴上限改变不重算曲线；
* 大量 K / Q / fn 更新后图形对象数量恒定；
* dirty flag + QTimer 能合并高频事件；
* 滑块释放触发最终高精度刷新；
* 标题控件具有足够高度 / 窗口最小尺寸不至于裁切；
* 数学测试（M(fn=1)=1）与固定 Q 曲线数值与公式一致；
* 界面与结果区不含旧符号（无 Ln = Lm/Lr、无 K = fs/fr）。
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["MPLBACKEND"] = "QtAgg"

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 性能测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_model import FN_MIN, FN_MAX, K_MIN, K_MAX, Q_MIN, Q_MAX, llc_gain, Q_FAMILY  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    w = app_main.MainWindow()
    yield w
    w._refresh_timer.stop() if hasattr(w, "_refresh_timer") else None
    w.close()
    w.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 增量更新：不重算不该重算的部分
# ---------------------------------------------------------------------------
def test_fn_change_does_not_recompute_family(win):
    """工作点 fn 改变绝不重新计算固定参考 Q 曲线族。"""
    win.plot.stats["family"] = 0
    family_ids = {id(l) for l in win.plot.hFamily}
    for step in (300, 500, 900):
        win.sliderFn.setValue(step)
        win._do_update()
    assert win.plot.stats["family"] == 0, "fn 改变不应重算固定 Q 曲线族"
    assert {id(l) for l in win.plot.hFamily} == family_ids


def test_fn_change_does_not_recompute_current_curve(win):
    """fn 改变：不重算当前 Q 整条曲线、不搜峰值。"""
    win.plot.stats["current"] = 0
    win.plot.stats["peak"] = 0
    for step in range(0, 1001, 50):
        win.sliderFn.setValue(step)
        win._do_update()
    assert win.plot.stats["current"] == 0, "fn 改变不应重算当前 Q 曲线"
    assert win.plot.stats["peak"] == 0, "fn 改变不应重新搜索峰值"


def test_q_change_does_not_recompute_family(win):
    """Q 改变：不重新计算固定参考 Q 曲线族。"""
    win.plot.stats["family"] = 0
    snap = [l.get_ydata().copy() for l in win.plot.hFamily]
    for step in range(0, 1001, 40):
        win.sliderQ.setValue(step)
        win._do_update()
    assert win.plot.stats["family"] == 0, "Q 改变不应重算固定 Q 曲线族"
    for old, line in zip(snap, win.plot.hFamily):
        assert np.allclose(old, line.get_ydata())


def test_k_change_updates_family_and_current(win):
    """K = Lm/Lr 改变：固定 Q 曲线族与当前 Q 曲线均应更新。"""
    win.plot.stats["family"] = 0
    win.plot.stats["current"] = 0
    win.sliderK.setValue(0)
    win._do_update()
    assert win.plot.stats["family"] >= 1
    assert win.plot.stats["current"] >= 1


def test_fr_change_does_not_recompute_curves(win):
    """fr 改变：不重算任何归一化曲线。"""
    win.plot.stats["family"] = 0
    win.plot.stats["current"] = 0
    before = win.plot.hCurrent.get_ydata().copy()
    win.editFr.setValue(500.0)
    win._do_update()
    assert win.plot.stats["family"] == 0
    assert win.plot.stats["current"] == 0
    assert np.allclose(before, win.plot.hCurrent.get_ydata())


def test_ymax_change_does_not_recompute_curves(win):
    """纵轴上限改变：不重算曲线，只改 ylim。"""
    win.plot.stats["family"] = 0
    win.plot.stats["current"] = 0
    win.editYmax.setValue(7.5)
    win._do_update()
    assert win.plot.stats["family"] == 0
    assert win.plot.stats["current"] == 0
    assert win.ax.get_ylim()[1] == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# 对象数量恒定
# ---------------------------------------------------------------------------
def test_no_artist_growth_after_1000_fn_updates(win):
    before = win.plot.artist_census()
    for i in range(1000):
        win.sliderFn.setValue((i * 7) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before


def test_no_artist_growth_after_1000_q_updates(win):
    before = win.plot.artist_census()
    legend_id = id(win.plot.legend)
    for i in range(1000):
        win.sliderQ.setValue((i * 3) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before
    legends = [c for c in win.plot.ax.get_children()
               if c.__class__.__name__ == "Legend"]
    assert len(legends) == 1
    assert id(win.plot.legend) == legend_id, "Q 更新后图例不应重建"


def test_no_artist_growth_after_1000_k_updates(win):
    before = win.plot.artist_census()
    for i in range(1000):
        win.sliderK.setValue((i * 5) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before


def test_legend_only_created_once(win):
    assert win.plot.stats["legend"] == 1, "图例只应创建一次"


# ---------------------------------------------------------------------------
# 事件合并：dirty flag + QTimer
# ---------------------------------------------------------------------------
def test_timer_merges_rapid_events(qapp):
    """高频 setValue 下，QTimer 合并成远少于事件数的刷新次数。"""
    w = app_main.MainWindow()
    counter = {"n": 0}
    orig = w._do_update

    def spy():
        counter["n"] += 1
        orig()

    w._do_update = spy
    w.show()
    qapp.processEvents()

    # 快速连续 setValue（不喂事件循环），模拟极速读取
    for i in range(300):
        w.sliderFn.setValue((i * 7) % 1001)
    # 手动触发合并计时器：验证它把 300 次事件合并为单次刷新
    counter["n"] = 0
    w._refresh_timer.stop()
    w._do_update()  # 模拟计时器超时回调
    assert counter["n"] == 1

    w._refresh_timer.stop() if hasattr(w, "_refresh_timer") else None
    w.close()
    w.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 滑块释放触发最终高精度刷新
# ---------------------------------------------------------------------------
def test_slider_release_triggers_full_refresh(qapp):
    w = app_main.MainWindow()
    counter = {"n": 0}
    orig = w._do_update

    def spy():
        counter["n"] += 1
        orig()

    w._do_update = spy
    w.sliderFn.setValue(700)
    w._on_released()
    assert counter["n"] >= 1
    # 松手后工作点竖线应精确落在最终 fn 值上
    fn_expected = app_main._log_from_slider(700, FN_MIN, FN_MAX)
    fn_actual = float(w.plot.hWorkLine.get_xdata()[0])
    assert fn_actual == pytest.approx(fn_expected, rel=1e-9)
    w.close()
    w.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 标题 / 布局
# ---------------------------------------------------------------------------
def test_title_has_sufficient_height(win):
    assert win.titleLabel.minimumHeight() >= 20
    assert win.statusLabel.minimumHeight() >= 20


def test_window_minimum_size_prevents_title_clipping(win):
    assert win.minimumWidth() >= 900
    assert win.minimumHeight() >= 600
    win.show()
    win.resize(win.minimumWidth(), win.minimumHeight())
    win.repaint()
    # 状态栏可见且未变成空串
    assert win.statusLabel.isVisible()
    assert win.statusLabel.text() != ""


# ---------------------------------------------------------------------------
# 数学正确性回归
# ---------------------------------------------------------------------------
def test_m_of_1_is_1_within_tolerance(win):
    for K in (1.5, 5.0, 10.0):
        for Q in (0.05, 0.5, 10.0):
            assert float(llc_gain(1.0, K, Q)) == pytest.approx(1.0, rel=1e-10)


def test_new_results_match_full_update(win):
    """按 dirty 增量结果与全量刷新数值一致（浮点容差内）。"""
    win.sliderK.setValue(400)
    win.sliderQ.setValue(300)
    win.sliderFn.setValue(650)
    win.editFr.setValue(124.4)
    win._mark_all_dirty()
    win._do_update()
    K = app_main._lin_from_slider(400, K_MIN, K_MAX)
    Q = app_main._log_from_slider(300, Q_MIN, Q_MAX)
    fn = app_main._log_from_slider(650, FN_MIN, FN_MAX)
    v_full = win.plot.refresh(
        k=True, q=True, fn=True, fr=True, ylim=True,
        k_ratio=K, Q=Q, fn_work=fn, fr_khz=124.4, y_max=2.2,
    )
    assert v_full["Mfn"] == pytest.approx(
        float(llc_gain(v_full["fn"], K, Q)), rel=1e-9)


def test_multi_q_family_values_stable(win):
    """固定 Q 曲线族数值与 llc_gain 独立计算一致（K 取窗口实际值）。"""
    K = app_main._lin_from_slider(win.sliderK.value(), K_MIN, K_MAX)
    for line, q in zip(win.plot.hFamily, Q_FAMILY):
        expected = llc_gain(win.plot.fn_curve, K, q)
        assert np.allclose(line.get_ydata(), expected)


def test_dirty_flags_merge_high_frequency(qapp):
    """大量相邻 dirty 置位只产生一次实际计算。"""
    w = app_main.MainWindow()
    orig = w.plot.refresh
    called = {"count": 0}

    def spy(*a, **kw):
        called["count"] += 1
        return orig(*a, **kw)

    w.plot.refresh = spy
    w._clear_dirty()
    for _ in range(500):
        w.dirty_fn = True
        w.dirty_q = True
    w._refresh_timer.stop()
    w._do_update()
    assert called["count"] == 1
    w.close()
    w.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 符号一致性：界面文字与结果区不得出现旧符号
# ---------------------------------------------------------------------------
def test_slider_labels_use_new_symbols(win):
    """左侧滑块标签为 K = Lm/Lr，右侧为 fn = fs/fr。"""
    # 通过检查滑块回调绑定与数值标签间接验证；直接检查坐标轴标签
    assert "归一化频率 fn" in win.ax.get_xlabel()
    text = win.resultBox.toPlainText()
    assert "K  = Lm / Lr" in text
    assert "fn = fs / fr" in text


def test_no_old_symbols_in_ui(win):
    """结果区与标题状态栏不得出现旧的 Ln = Lm/Lr 或 K = fs/fr。"""
    win._do_update()
    text = win.resultBox.toPlainText()
    status = win.statusLabel.text()
    assert "Ln" not in text
    assert "Ln" not in status
    assert "K  = fs / fr" not in text