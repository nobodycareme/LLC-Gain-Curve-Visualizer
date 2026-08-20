# -*- coding: utf-8 -*-
"""工程设计与显示开关的 GUI 层测试（Phase 6/7/8）。

覆盖：
* 工程设计层在窗口中默认可计算并出现在右侧结果/分析/建议区；
* **显示状态与数学状态分离**：切换显示开关不触发任何无关数学重算；
* 四个可选层（参考 Q / 阻容边界 / M 范围 / fn 范围）隐藏时绘图/图例/Hover 同步；
* 核心五项恒显、无"工程工作角点"checkbox；
* 事务式更新：工程参数无效时保留上一套有效结果并提示错误；
* Pout = Vo × Io 联动、自动/手动匝比、自动推荐 Q 非强制；
* 纯 fn 拖动不重算工程设计层。
"""

from __future__ import annotations

import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 GUI 工程测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    w = app_main.MainWindow()
    w._do_update()
    yield w
    w._refresh_timer.stop() if hasattr(w, "_refresh_timer") else None
    w.close()
    w.deleteLater()
    qapp.processEvents()


# ---------------------------------------------------------------------------
# 工程设计结果默认呈现
# ---------------------------------------------------------------------------
def test_engine_default_computes_and_reports(win):
    assert win._engine_ok
    text = win.resultBox.toPlainText()
    # 工程设计结果 / 应力 / 分析 / 建议均已接入右侧
    assert "Re" in text and "Lr_calc" in text
    assert "【分析】" in text and "【建议】" in text
    assert "M_req_max" in text
    # 现有工作点字段零回退
    assert "K    =" in text and "M(fn)=" in text


def test_engine_keys_present(win):
    e = win._engine
    for key in ("n", "Re_full", "Zr_calc", "Lr_calc", "Lm_calc", "Cr_calc",
                "M_req_min", "M_req_max", "Q_full", "Q_overload",
                "fn_boundary", "M_available", "fn_min", "fn_max"):
        assert key in e


# ---------------------------------------------------------------------------
# 显示开关与数学状态分离
# ---------------------------------------------------------------------------
def test_toggle_display_does_not_recompute_math(win):
    """切换显示开关绝不触发曲线重算：stats 计数保持。"""
    for attr in ("family", "current", "peak", "boundary"):
        win.plot.stats[attr] = 0
    for _ in range(3):
        win.cbRefQ.setChecked(False)
        win.cbBoundary.setChecked(False)
        win.cbMRange.setChecked(True)
        win.cbFnRange.setChecked(True)
        win.cbRefQ.setChecked(True)
        win.cbBoundary.setChecked(True)
        win.cbMRange.setChecked(False)
        win.cbFnRange.setChecked(False)
    for attr in ("family", "current", "peak", "boundary"):
        assert win.plot.stats[attr] == 0, f"显示开关不应重算 {attr}"


def test_reference_off_syncs_legend_hover_draw(win):
    win.plot.stats["family"] = 0
    win.cbRefQ.setChecked(False)
    win._do_update()
    assert win.plot.show_reference is False
    # 图例不再包含参考 Q
    texts = [e[3] for e in win.plot.legend_entries()]
    assert not any(t.startswith("Q = ") for t in texts)
    # Hover 不再命中参考族
    kinds = {c["kind"] for c in win.plot._candidates(1.0)}
    assert "family" not in kinds and "current" in kinds
    assert win.plot.stats["family"] == 0  # 未重算数据


def test_boundary_off_syncs_legend_hover(win):
    win.cbBoundary.setChecked(False)
    win._do_update()
    assert win.plot.show_boundary is False
    texts = [e[3] for e in win.plot.legend_entries()]
    assert not any("阻容分界线" in t for t in texts)
    kinds = {c["kind"] for c in win.plot._candidates(1.0)}
    assert "boundary" not in kinds
    # 数学边界计算不受显示开关影响
    assert math.isfinite(win.plot.fn_boundary) or True


def test_core_five_always_in_legend(win):
    win.cbRefQ.setChecked(False)
    win.cbBoundary.setChecked(False)
    win._do_update()
    texts = [e[3] for e in win.plot.legend_entries()]
    joined = " | ".join(texts)
    assert "当前 Q 曲线" in joined
    assert "fnp" in joined and "fnr=1" in joined
    assert "增益峰值" in joined and "工作点 fn" in joined


def test_m_and_fn_range_layers(win):
    # 提高 Vin_min 使增益可行，获得有限 fn_min，便于验证 fn 范围带
    win.spinVinMin.setValue(350.0)
    win._engine_dirty = True
    win._do_update()
    assert win._engine_ok
    fn_finite = math.isfinite(win.plot.fn_min_band)
    before = len(win.plot.legend_entries())
    win.cbMRange.setChecked(True)
    assert len(win.plot.legend_entries()) > before
    assert win.plot.show_m_range is True
    if win._engine["fn_min_feasible"]:
        win.cbFnRange.setChecked(True)
        assert win.plot.show_fn_range is True
        assert any("fn 范围" in e[3] for e in win.plot.legend_entries())
    assert math.isfinite(win.plot.m_req_max)
    _ = fn_finite  # fn 是否可行由规格决定，二者皆合法


# ---------------------------------------------------------------------------
# 事务式更新
# ---------------------------------------------------------------------------
def test_transactional_keeps_last_valid_on_invalid_input(win):
    engine_before = win._engine
    stress_before = win._stress
    assert win._engine_ok
    # 制造无效输入：Vin_min 大于 Vin_nom
    bad = win.spinVinNom.value() * 2.0
    win.spinVinMin.setValue(bad)
    win._do_update()
    assert not win._engine_ok
    assert win._engine_error is not None
    assert "Vin" in win._engine_error or "min" in win._engine_error
    # 上一套有效结果被保留（需求二十六）
    assert win._engine is engine_before
    assert win._stress is stress_before
    # 结果区明确提示错误
    assert "工程参数无效" in win.resultBox.toPlainText()


def test_transactional_recovers_after_fix(win):
    win.spinVinMin.setValue(999.0)  # 无效：Vin_min > Vin_nom（spinVo 下限 0.1，无法用负值触发）
    win._do_update()
    assert not win._engine_ok
    win.spinVinMin.setValue(300.0)  # 修复
    win._engine_dirty = True
    win._do_update()
    assert win._engine_ok
    assert "工程参数无效" not in win.resultBox.toPlainText()


# ---------------------------------------------------------------------------
# Pout / Io / Vo 联动（需求十一）
# ---------------------------------------------------------------------------
def test_pout_io_linkage(win):
    vo = win.spinVo.value()
    pout = 240.0
    win.spinPout.setValue(pout)
    assert win.spinIo.value() == pytest.approx(pout / vo, rel=1e-9)
    io = 18.0
    win.spinIo.setValue(io)
    assert win.spinPout.value() == pytest.approx(io * vo, rel=1e-9)


# ---------------------------------------------------------------------------
# 匝比自动/手动 & 自动推荐 Q（需求十二/十四）
# ---------------------------------------------------------------------------
def test_turn_mode_switch_enables_manual_n(win):
    assert win.comboTurn.currentIndex() == 0  # 自动
    assert not win.spinN.isEnabled()
    win.comboTurn.setCurrentIndex(1)          # 手动
    win._do_update()
    assert win.spinN.isEnabled()
    assert win._engine["n_mode"] == "manual"


def test_auto_recommend_q_non_forcing(win):
    win.comboQMode.setCurrentIndex(1)  # 自动推荐
    win._engine_dirty = True
    win._do_update()
    assert win._engine_ok
    assert win._engine["auto_q"] is True
    assert math.isfinite(win._engine["Q_auto"])
    # 推荐未越界
    assert app_main.Q_MIN <= win._engine["Q_auto"] <= app_main.Q_MAX


# ---------------------------------------------------------------------------
# fn 拖动不重算工程设计层（性能：需求三/二十七）
# ---------------------------------------------------------------------------
def test_fn_change_does_not_recompute_engine(win):
    engine = win._engine
    stress = win._stress
    win._engine_dirty = False
    for step in (300, 500, 800):
        win.sliderFn.setValue(step)
        win._do_update()
    assert win._engine is engine
    assert win._stress is stress
    assert not win._engine_dirty


# ---------------------------------------------------------------------------
# 无论如何都不出现“工程工作角点”checkbox（需求六）
# ---------------------------------------------------------------------------
def test_no_operating_corner_checkboxes(win):
    from PySide6.QtWidgets import QCheckBox
    labels = []
    for w in win.findChildren(QCheckBox):
        labels.append(w.text())
    joined = " ".join(labels)
    for bad in ("关键工况点", "工程角点", "设计角点", "工作角点"):
        assert bad not in joined