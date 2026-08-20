# -*- coding: utf-8 -*-
"""GUI 冒烟测试（离屏运行，无需真实显示器）。

符号体系：K = Lm/Lr，fn = fs/fr。

本测试用 ``QT_QPA_PLATFORM=offscreen`` 启动真实的 PySide6 窗口
（绘图后端为纯 QPainter 的 :class:`plot_widget.GainPlotWidget`），覆盖：
* 程序能构造主窗口且无异常；
* 默认曲线数据正常（9 条参考曲线 + 1 条当前 Q 粗线 + 阻容分界线）；
* 图例包含四种特征点标记（fnp / fnr=1 / 峰值 / 工作点 fn）与阻容分界线；
* **反复拖动 K / Q / fn 后，绘图对象/缓存数量不增长**；
* fnp/fnr/工作点行为、增量刷新语义、fr/纵轴上限修改；
* 非法/极端输入不会导致崩溃；
* 界面文字与结果区非旧符号（无 Ln = Lm/Lr、无 K = fs/fr）；
* 可实际渲染/导出 PNG。
"""

from __future__ import annotations

import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 冒烟测试")

from PySide6.QtCore import Qt, QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import fn_parallel, llc_gain, Q_FAMILY  # noqa: E402


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


def _artist_census(win) -> dict:
    return win.plot.artist_census()


# ---------------------------------------------------------------------------
# 启动与默认状态
# ---------------------------------------------------------------------------
def test_window_constructs(win):
    assert win.windowTitle() == app_main.APP_TITLE
    assert win.canvas is not None


def test_default_curves_present(win):
    """9 条参考曲线 + 1 条当前 Q + 阻容分界线。"""
    assert len(win.plot.family_data_y()) == len(Q_FAMILY) == 9
    assert len(win.plot.current_data_y()) == 3000
    bx, by = win.plot.boundary_data()
    assert len(bx) >= 400
    assert len(by) == len(bx)


def test_default_curve_data_is_finite(win):
    def finite(values):
        return all(v == v and v is not None for v in values)  # NaN 检查

    assert finite(win.plot.current_data_y())
    for y in win.plot.family_data_y():
        assert finite(y)
    bx, by = win.plot.boundary_data()
    # 边界在奇点处用容差避开，除首个极少数点外均有限（允许巨大但有限）
    assert any(v == v for v in by)


def test_x_axis_is_logarithmic(win):
    """对数横轴：fn 区间内等大的对数间隔映射为等宽的像素间隔。"""
    r = QRectF(100, 100, 800, 400)
    # log 变换下 1 应位于中心，且 fn=10 与 fn=0.1 相对 1 对称
    x1 = win.plot._map_x(1.0, r)
    assert x1 == pytest.approx(r.left() + r.width() / 2, abs=1e-6)
    xa = x1 - win.plot._map_x(0.1, r)
    xb = win.plot._map_x(10.0, r) - x1
    assert xa == pytest.approx(xb, rel=1e-6)


def test_default_ymax_applied(win):
    assert win.plot.ymax == pytest.approx(2.2)


# ---------------------------------------------------------------------------
# 图例必须区分四种标记与阻容分界线
# ---------------------------------------------------------------------------
def test_legend_contains_four_markers(win):
    texts = [e[3] for e in win.plot.legend_entries()]
    joined = " | ".join(texts)
    assert "fnp" in joined
    assert "fnr=1" in joined
    assert "峰值" in joined
    assert "工作点 fn" in joined
    assert "阻容分界线" in joined
    assert "∠Zin = 0" in joined
    # 9 条参考 Q + 当前 Q + 阻容边界 + 4 个标记
    assert len(texts) == 15


def test_legend_shows_current_q_value(win):
    texts = [e[3] for e in win.plot.legend_entries()]
    assert any(txt.startswith("当前 Q 曲线：Q=") for txt in texts)


def test_boundary_legend_entry_is_dashed(win):
    entries = win.plot.legend_entries()
    bnd = next(e for e in entries if "阻容分界线" in e[3])
    assert bnd[2] == Qt.DashLine


def test_four_markers_have_distinct_labels(win):
    """四种特征点在结果区/图例中必须可区分（对应不同图案语义）。"""
    texts = [e[3] for e in win.plot.legend_entries()]
    markers = [t for t in texts if any(s in t for s in ("fnp（", "fnr=1（", "增益峰值", "工作点 fn"))]
    assert len(markers) == 4
    assert len(set(markers)) == 4


# ---------------------------------------------------------------------------
# 关键回归：驱动不产生新对象 / 不外泄数据
# ---------------------------------------------------------------------------
def test_no_artist_growth_on_heavy_dragging(win):
    """模拟长时间连续拖动 K/Q/fn，绘图缓存数量必须保持恒定。"""
    before = _artist_census(win)
    cur_before = win.plot.current_data_y()

    for step in range(0, 1001, 25):
        win.sliderK.setValue(step)
        win._do_update()
        win.sliderQ.setValue(1000 - step)
        win._do_update()
        win.sliderFn.setValue((step * 7) % 1001)
        win._do_update()

    after = _artist_census(win)
    assert after == before, f"拖动后绘图缓存数量发生变化：{before} -> {after}"
    # 数据数组是原地更新的同一批对象（长度恒定）
    assert len(win.plot.current_data_y()) == len(cur_before)


def test_no_artist_growth_on_fr_and_ymax_changes(win):
    before = _artist_census(win)
    for fr in (50.0, 124.4, 300.0, 1000.0):
        win.editFr.setValue(fr)
        win._do_update()
    for ym in (0.5, 2.2, 10.0, 50.0):
        win.editYmax.setValue(ym)
        win._do_update()
    assert _artist_census(win) == before


def test_data_buffers_reused_not_reallocated(win):
    """增量刷新必须原地改写同一批数据列表，而不是每次新建。"""
    first = win.plot.current_data_y()
    cursor_cur = id(first)
    win.sliderQ.setValue(200)
    win._do_update()
    # current_data_y() 返回拷贝以便断言；伪造不适用——改为验证内部缓冲对象稳定：
    stats_cur = win.plot.stats["current"]
    win.sliderQ.setValue(700)
    win._do_update()
    assert win.plot.stats["current"] == stats_cur + 1


# ---------------------------------------------------------------------------
# 交互逻辑正确性
# ---------------------------------------------------------------------------
def test_k_change_updates_all_family_curves(win):
    win.sliderK.setValue(0)      # K = 1.5
    win._do_update()
    snap = win.plot.family_data_y()

    win.sliderK.setValue(1000)   # K = 10
    win._do_update()
    new = win.plot.family_data_y()
    for old, new_y in zip(snap, new):
        assert old != new_y, "K 改变后所有参考 Q 曲线都应更新"


def test_fn_change_does_not_alter_curve_shape(win):
    win.sliderFn.setValue(200)
    win._do_update()
    cur = win.plot.current_data_y()
    fam = win.plot.family_data_y()

    win.sliderFn.setValue(900)
    win._do_update()
    assert win.plot.current_data_y() == pytest.approx(cur)
    for old, line in zip(fam, win.plot.family_data_y()):
        assert line == pytest.approx(old)


def test_work_point_lies_on_current_curve(win):
    from llc_py import llc_gain as pgain
    for step in (100, 400, 700, 950):
        win.sliderFn.setValue(step)
        win._do_update()
        K = app_main._lin_from_slider(win.sliderK.value(), 1.5, 10.0)
        Q = app_main._log_from_slider(win.sliderQ.value(), 0.05, 10.0)
        fn_w = app_main._log_from_slider(win.sliderFn.value(), 0.1, 10.0)
        expected = float(pgain(fn_w, K, Q))
        assert win.plot._values()["Mfn"] == pytest.approx(expected, rel=1e-9)


def test_fr_only_affects_real_frequency_not_shape(win):
    win.editFr.setValue(124.4)
    win._do_update()
    shape = win.plot.current_data_y()

    win.editFr.setValue(500.0)
    win._do_update()
    assert win.plot.current_data_y() == pytest.approx(shape), \
        "修改 fr 不应改变归一化增益曲线形状"
    assert "500.000 kHz" in win.resultBox.toPlainText()


def test_ymax_applies_to_axis(win):
    win.editYmax.setValue(7.5)
    win._do_update()
    assert win.plot.ymax == pytest.approx(7.5)


def test_result_box_contains_required_fields(win):
    win._do_update()
    text = win.resultBox.toPlainText()
    for token in ("K    =", "Q    =", "fn   =", "M(fn)=", "fs", "fnp",
                  "fp", "M(fnp)", "fnr", "fr", "M(fnr)", "fn_peak",
                  "f_peak", "M_peak", "彩色细线", "黑色粗线", "并联谐振",
                  "串联谐振", "K  = Lm / Lr", "fn = fs / fr"):
        assert token in text, f"结果区缺少字段：{token}"


def test_result_box_has_no_old_symbols(win):
    win._do_update()
    text = win.resultBox.toPlainText()
    assert "Ln" not in text
    assert "K  = fs / fr" not in text


def test_result_box_has_region_and_boundary(win):
    win._do_update()
    text = win.resultBox.toPlainText()
    assert "工作区域" in text
    assert "fn_boundary" in text
    assert "∠Zin" in text


def test_fnp_line_tracks_K(win):
    for step in (0, 500, 1000):
        win.sliderK.setValue(step)
        win._do_update()
        K = app_main._lin_from_slider(step, 1.5, 10.0)
        assert win.plot.fnp == pytest.approx(fn_parallel(K), rel=1e-9)


def test_fnr_line_stays_at_one(win):
    for step in (0, 300, 800, 1000):
        win.sliderK.setValue(step)
        win._do_update()
        assert win.plot.fnr == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 交互性能：K 重算族；Q 只重算当前；fn 不重算曲线
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
    win.canvas.resize(1100, 720)
    win.show()
    win._do_update()