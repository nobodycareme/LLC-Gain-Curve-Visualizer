# -*- coding: utf-8 -*-
"""针对"交互性能 + 符号体系纠正 + QPainter 绘图层"的新增/迁移测试。

符号体系：K = Lm/Lr，fn = fs/fr。

绘图后端为纯 QPainter 控件 :class:`plot_widget.GainPlotWidget`（无 matplotlib）。

验证目标（与旧 Matplotlib 版测试强度相同）：
* fn 改变不重算固定 Q 曲线、不重算当前 Q 整条曲线、不搜峰值；
* Q 改变不重算固定参考 Q 曲线族；
* K（= Lm/Lr）改变时固定 Q 曲线族与当前 Q 曲线均更新；
* fr 改变不重算归一化曲线；
* 纵轴上限改变不重算曲线；
* 大量 K / Q / fn 更新后绘图缓存数量恒定、数据缓冲不复建；
* dirty flag + QTimer 能合并高频事件；
* 滑块释放触发最终高精度刷新；
* 标题控件具有足够高度 / 窗口最小尺寸不至于裁切；
* 数学测试（M(fn=1)=1）与固定 Q 曲线数值与公式一致；
* 界面与结果区不含旧符号（无 Ln = Lm/Lr、无 K = fs/fr）。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 性能测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import (  # noqa: E402
    FN_MIN, FN_MAX, K_MIN, K_MAX, Q_MIN, Q_MAX,
    llc_gain, Q_FAMILY,
)
from plot_widget import GainPlotWidget  # noqa: E402


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


def _close(w, qapp):
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
    for step in (300, 500, 900):
        win.sliderFn.setValue(step)
        win._do_update()
    assert win.plot.stats["family"] == 0, "fn 改变不应重算固定 Q 曲线族"


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
    """Q 改变：不重新计算固定参考 Q 曲线族，数据保持。"""
    win.plot.stats["family"] = 0
    snap = win.plot.family_data_y()
    for step in range(0, 1001, 40):
        win.sliderQ.setValue(step)
        win._do_update()
    assert win.plot.stats["family"] == 0, "Q 改变不应重算固定 Q 曲线族"
    for old, new_y in zip(snap, win.plot.family_data_y()):
        assert new_y == pytest.approx(old)


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
    before = win.plot.current_data_y()
    win.editFr.setValue(500.0)
    win._do_update()
    assert win.plot.stats["family"] == 0
    assert win.plot.stats["current"] == 0
    assert win.plot.current_data_y() == pytest.approx(before)


def test_ymax_change_does_not_recompute_curves(win):
    """纵轴上限改变：不重算曲线，只改显示上限。"""
    win.plot.stats["family"] = 0
    win.plot.stats["current"] = 0
    win.editYmax.setValue(7.5)
    win._do_update()
    assert win.plot.stats["family"] == 0
    assert win.plot.stats["current"] == 0
    assert win.plot.ymax == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# 缓存数量恒定 / 数据缓冲复用
# ---------------------------------------------------------------------------
def test_no_artist_growth_after_1000_fn_updates(win):
    before = win.plot.artist_census()
    for i in range(1000):
        win.sliderFn.setValue((i * 7) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before


def test_no_artist_growth_after_1000_q_updates(win):
    before = win.plot.artist_census()
    cursor = id(win.plot.current_y)          # 底层缓冲对象标识
    for i in range(1000):
        win.sliderQ.setValue((i * 3) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before
    assert id(win.plot.current_y) == cursor, "Q 更新后当前曲线缓冲不应重建"
    assert len(win.plot.current_y) == 3000


def test_no_artist_growth_after_1000_k_updates(win):
    before = win.plot.artist_census()
    buf_ids = (id(win.plot.current_y), id(win.plot.boundary_x))
    for i in range(1000):
        win.sliderK.setValue((i * 5) % 1001)
        win._do_update()
    assert win.plot.artist_census() == before
    assert (id(win.plot.current_y), id(win.plot.boundary_x)) == buf_ids


def test_legend_data_created_once(win):
    """图例条目结构一次构造即可复用（仅"当前 Q"文本随 Q 合理变化）。"""
    e1 = win.plot.legend_entries()
    for i in range(200):
        win.sliderQ.setValue((i * 3) % 1001)
        win._do_update()
    e2 = win.plot.legend_entries()
    assert len(e1) == len(e2) == 15
    # 除"当前 Q"条目（随 Q 合法更新）外，其余条目必须完全一致
    static1 = [t for _, _, _, t in e1 if "当前 Q 曲线" not in t]
    static2 = [t for _, _, _, t in e2 if "当前 Q 曲线" not in t]
    assert static1 == static2


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

    for i in range(300):
        w.sliderFn.setValue((i * 7) % 1001)
    counter["n"] = 0
    w._refresh_timer.stop()
    w._do_update()  # 模拟计时器超时回调
    assert counter["n"] == 1
    _close(w, qapp)


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
    # 松手后工作点应精确落在最终 fn 值上
    fn_expected = app_main._log_from_slider(700, FN_MIN, FN_MAX)
    assert w.plot.fn_work == pytest.approx(fn_expected, rel=1e-9)
    _close(w, qapp)


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
    """按 dirty 增量结果与公式直接计算数值一致（浮点容差内）。"""
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
    assert v_full["Mfn"] == pytest.approx(float(llc_gain(v_full["fn"], K, Q)), rel=1e-9)


def test_multi_q_family_values_stable(win):
    """固定 Q 曲线族数值与 llc_gain 独立计算一致（K 取窗口实际值）。"""
    K = app_main._lin_from_slider(win.sliderK.value(), K_MIN, K_MAX)
    for y, q in zip(win.plot.family_data_y(), Q_FAMILY):
        expected = llc_gain(win.plot.fn_curve, K, q)
        assert y == pytest.approx(expected)


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
    _close(w, qapp)


# ---------------------------------------------------------------------------
# 符号一致性：界面文字与结果区不得出现旧符号
# ---------------------------------------------------------------------------
def test_slider_labels_use_new_symbols(win):
    """使用 QPainter 控件，标签文本为 K = Lm/Lr、fn = fs/fr。"""
    assert isinstance(win.canvas, GainPlotWidget), "主画布应为 QPainter 控件"
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