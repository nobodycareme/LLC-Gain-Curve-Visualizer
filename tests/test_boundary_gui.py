# -*- coding: utf-8 -*-
"""阻容分界线在 GUI 层（QPainter 绘图控件）的行为测试。

验证：
* 阻容分界线数据存在且随 K（= Lm/Lr）改变而更新；
* 工作区域判据（感性/容性/边界）来自 ∠Zin=0，而非肉眼/峰值；
* fn 跨过边界时区域判定随之变化；
* 结果区文本包含区域与边界信息；
* 分界线数据缓冲数量恒定（不随 K/Q/fn 拖动增长）。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import (  # noqa: E402
    boundary_frequency,
    boundary_gain,
    fn_parallel,
    llc_gain,
    llc_input_impedance_normalized,
)


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


def _set_sliders_and_update(win, K=None, Q=None, fn=None):
    if K is not None:
        win.sliderK.setValue(app_main._slider_from_lin(K, app_main.K_MIN, app_main.K_MAX))
        win.dirty_k = True
    if Q is not None:
        win.sliderQ.setValue(app_main._slider_from_log(Q, app_main.Q_MIN, app_main.Q_MAX))
        win.dirty_q = True
    if fn is not None:
        win.sliderFn.setValue(app_main._slider_from_log(fn, app_main.FN_MIN, app_main.FN_MAX))
        win.dirty_fn = True
    win._do_update()


def _all_finite(values):
    """NaN 检查（不含 Inf，边界允许大有限值）。"""
    return all(v == v for v in values)


def test_boundary_line_exists(win):
    """主图必须包含阻容分界线数据。"""
    x, y = win.plot.boundary_data()
    assert len(x) >= 400
    assert len(y) == len(x)
    # 除接近奇点的首点外，边界数据应基本有限；用相对容差避开奇点
    assert any(v == v for v in y), "边界数据不得全为 NaN"


def test_boundary_line_matches_analytic_solution(win):
    """绘图中的分界线数据必须与分析 Mb(fn) 公式一致（以窗口实际 K 为准）。"""
    x, y = win.plot.boundary_data()
    K = win.plot.K                              # 窗口实际使用的 K
    fm0 = fn_parallel(K)
    ref = boundary_gain(x, K)
    # NaN(区间外)/极大(奇点)统一归一后再比较
    def norm(v):
        return 0.0 if v != v or v > 1e6 else float(v)
    assert all(norm(a) == pytest.approx(norm(b), abs=1e-6)
               for a, b in zip(y, ref))
    # 边界 x 范围在 (fm0, 1) 内，首点有限（奇点已用容差避开）
    assert x[0] > fm0 and x[-1] < 1.0


def test_boundary_recomputes_on_k_change(win):
    """K 改变后分界线数据必须随之更新。"""
    _set_sliders_and_update(win, K=2.0)
    _, y_k2 = win.plot.boundary_data()
    _set_sliders_and_update(win, K=8.0)
    x_k8, y_k8 = win.plot.boundary_data()
    assert y_k2 != y_k8, "K 改变后分界线必须重算"
    fm0 = fn_parallel(win.plot.K)
    assert abs(x_k8[0] - fm0 * (1.0 + 1e-6)) < 1e-4


def test_boundary_frequency_limit_fnp(win):
    """边界曲线左端应始于 fnp = 1/sqrt(1+K)（Mb→+∞ 侧）。"""
    x, _ = win.plot.boundary_data()
    assert x[0] > fn_parallel(win.plot.K)


def test_work_region_inductive_right_of_boundary(win):
    """fn 位于边界右侧（更高）时应判为感性区。"""
    K, Q = 5.0, 0.5
    fb = boundary_frequency(K, Q)
    _set_sliders_and_update(win, K=K, Q=Q, fn=fb * 1.2)
    assert win.plot.region == "inductive"


def test_work_region_capacitive_left_of_boundary(win):
    """fn 位于边界左侧（更低）时应判为容性区。"""
    K, Q = 5.0, 0.5
    fb = boundary_frequency(K, Q)
    _set_sliders_and_update(win, K=K, Q=Q, fn=fb * 0.8)
    assert win.plot.region == "capacitive"


def test_region_directly_from_zin_imag(win):
    """区域判定必须与 Im(Zin) 符号逐点一致，不能靠肉眼位置。"""
    K, Q = 5.0, 0.5
    fb = boundary_frequency(K, Q)
    for fn_t in (fb * 0.85, fb * 1.15):
        _set_sliders_and_update(win, K=K, Q=Q, fn=fn_t)
        z = llc_input_impedance_normalized(fn_t, K, Q)
        im = float(z.imag)
        expected = "inductive" if im > 0 else "capacitive"
        assert win.plot.region == expected


def test_region_zero_im_near_boundary(win):
    """在边界频率处 Im(Zin)≈0。"""
    K, Q = 5.0, 0.5
    fb = boundary_frequency(K, Q)
    im = float(llc_input_impedance_normalized(fb, K, Q).imag)
    assert abs(im) < 1e-3, "边界频率处 Im(Zin) 应接近 0"


def test_boundary_frequency_matches_model(win):
    """窗口内边界交点频率必须与模型一致（以滑块量化后的实际 K/Q 为准）。"""
    K, Q, _, _, _ = win._read_params()
    assert win.plot.fn_boundary == pytest.approx(boundary_frequency(K, Q), abs=1e-9)
    assert win.plot.mboundary == pytest.approx(
        llc_gain(boundary_frequency(K, Q), K, Q), rel=1e-9)


def test_result_text_contains_region_and_boundary(win):
    _set_sliders_and_update(win, K=5.0, Q=0.5, fn=1.1)
    text = win.resultBox.toPlainText()
    assert "工作区域" in text
    assert "感性区" in text or "容性区" in text or "阻容边界" in text
    assert "fn_boundary" in text
    assert "∠Zin" in text


def test_boundary_buffer_stable_under_drag(win):
    """大量 K/Q/fn 拖动后，分界数据缓冲数量与对象标识不变。"""
    census_before = win.plot.artist_census()
    buf_ids = (id(win.plot.boundary_x), id(win.plot.boundary_y))
    before_stat = win.plot.stats["boundary"]
    for i in range(60):
        K = 1.5 + (10.0 - 1.5) * (i / 59)
        Q = 10 ** (-1.0 + 2.0 * ((i % 30) / 29))
        fn = 10 ** (-1.0 + 2.0 * ((i % 19) / 18))
        win.dirty_k = win.dirty_q = win.dirty_fn = True
        win._do_update()
    assert win.plot.artist_census() == census_before
    assert (id(win.plot.boundary_x), id(win.plot.boundary_y)) == buf_ids
    assert win.plot.stats["boundary"] > before_stat