# -*- coding: utf-8 -*-
"""llc_design（工程设计纯数学层）单元测试。"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_design as d  # noqa: E402


# ---- 拓扑常数 ----
def test_gain_constant():
    assert d.gain_constant("half") == 2.0
    assert d.gain_constant("full") == 1.0
    with pytest.raises(ValueError):
        d.gain_constant("bad")


# ---- 整流压降 ----
def test_rectifier_output_offset():
    assert d.rectifier_output_offset("ct_diode", 0.7) == pytest.approx(0.7)
    assert d.rectifier_output_offset("fb_diode", 0.7) == pytest.approx(1.4)
    assert d.rectifier_output_offset("ct_sr", 0.05) == pytest.approx(0.05)
    assert d.rectifier_output_offset("fb_sr", 0.05) == pytest.approx(0.10)
    with pytest.raises(ValueError):
        d.rectifier_output_offset("unknown", 0.5)


# ---- 匝比 ----
def test_turns_ratio_auto_half():
    n = d.turns_ratio_auto("half", 390.0, 12.0, 0.0)
    assert n == pytest.approx(390.0 / 24.0)  # 16.25


def test_turns_ratio_auto_full():
    n = d.turns_ratio_auto("full", 390.0, 12.0, 0.0)
    assert n == pytest.approx(390.0 / 12.0)


# ---- 所需增益 ----
def test_m_required():
    n = 16.0
    assert d.m_required("half", n, 12.0, 0.0, 300.0) == pytest.approx(2 * 16 * 12 / 300)
    assert d.m_required("full", n, 12.0, 0.0, 300.0) == pytest.approx(16 * 12 / 300)
    with pytest.raises(ValueError):
        d.m_required("half", n, 12.0, 0.0, 0.0)


# ---- 负载与等效负载 ----
def test_load_and_equiv_resistance():
    rl = d.load_resistance(12.0, 300.0)
    assert rl == pytest.approx(144.0 / 300.0)
    re = d.equivalent_resistance(16.0, rl)
    assert re == pytest.approx(8.0 * 256.0 * rl / math.pi ** 2)
    re2 = d.re_from_spec(16.0, 12.0, 300.0)
    assert re2 == pytest.approx(8.0 * 256.0 * 144.0 / (math.pi ** 2 * 300.0))


def test_load_resistance_requires_pout_positive():
    with pytest.raises(ValueError):
        d.load_resistance(12.0, 0.0)


# ---- 谐振腔 ----
def test_resonant_tank_formulas():
    fr, re, q, k = 130e3, 99.7, 0.47, 5.0
    t = d.resonant_tank(fr, re, q, k)
    zr = q * re                     # 必须是 Q·Re，绝不 Re/Q
    assert t["Zr"] == pytest.approx(zr)
    assert t["Lr"] == pytest.approx(zr / (2 * math.pi * fr))
    assert t["Cr"] == pytest.approx(1.0 / (2 * math.pi * fr * zr))
    assert t["Lm"] == pytest.approx(k * t["Lr"])


def test_resonant_tank_zr_never_re_div_q():
    # 直接构造：任何 Q>1 时若误用 Re/Q 将显著不同
    t = d.resonant_tank(100e3, 100.0, 2.0, 5.0)
    assert t["Zr"] == pytest.approx(200.0)   # Q·Re 而非 50.0


def test_q_from_re():
    assert d.q_from_re(46.9, 99.7) == pytest.approx(46.9 / 99.7)


# ---- 实际参数反算 ----
def test_back_calc_actual():
    r = d.back_calc_actual(60e-6, 27.3e-9, 210e-6)
    assert r["K"] == pytest.approx(3.5)
    assert r["fr"] == pytest.approx(1.0 / (2 * math.pi * math.sqrt(60e-6 * 27.3e-9)),
                                    rel=1e-9)
    assert r["Zr"] == pytest.approx(math.sqrt(60e-6 / 27.3e-9), rel=1e-9)


# ---- 推荐 Q ----
def test_recommend_q_monotonic_margin():
    # 更高增益需求 → 更低推荐 Q
    q1 = d.recommend_q(3.5, 1.20, margin=1.05)
    q2 = d.recommend_q(3.5, 1.40, margin=1.05)
    assert q2 < q1
    assert 0.05 < q1 < 6.0


# ---- 校验 ----
def _spec(**over):
    base = dict(bridge="half", rect="ct_diode",
                vin_min=300.0, vin_nom=390.0, vin_max=400.0, vo=12.0,
                pout=300.0, vdrop=0.0, efficiency=1.0, overload=1.1,
                turn_mode="manual", n_manual=16.0, fr_hz=124.4e3, k=3.5,
                q_selected=0.5)
    base.update(over)
    return d.DesignSpec(**base)


def test_validate_ok():
    assert d.validate_spec(_spec()) == []


@pytest.mark.parametrize("field,value,msg", [
    ("vin_min", 0.0, "Vin_min"),
    ("vin_max", -1.0, "Vin_max"),
    ("vo", 0.0, "Vo"),
    ("pout", 0.0, "Pout"),
    ("efficiency", 0.0, "效率"),
    ("efficiency", 1.5, "效率"),
    ("fr_hz", 0.0, "fr"),
    ("k", 0.0, "K"),
    ("q_selected", -1.0, "Q"),
])
def test_validation_rejects(field, value, msg):
    errs = d.validate_spec(_spec(**{field: value}))
    assert any(msg in e for e in errs)


def test_validation_vin_order():
    assert d.validate_spec(_spec(vin_nom=200.0, vin_min=300.0))  # nom<min 报错
    assert any("Vin_nom" in e for e in d.validate_spec(_spec(vin_nom=200.0, vin_min=300.0)))


# ---- 顶层设计计算 ----
def test_compute_design_full():
    r = d.compute_design(_spec())
    # n=16, 半桥，Vdrop=0
    assert r["n"] == pytest.approx(16.0)
    assert r["M_req_max"] == pytest.approx(2 * 16 * 12 / 300.0)
    assert r["M_req_min"] == pytest.approx(2 * 16 * 12 / 400.0)
    assert r["Re_full"] == pytest.approx(8.0 * 256.0 * 144.0 / (math.pi ** 2 * 300.0))
    # 过载 Re 更低 → Q 更高
    assert r["Re_overload"] < r["Re_full"]
    assert r["Q_overload"] > r["Q_full"]
    # Zr = Q_selected * Re_full
    assert r["Zr_calc"] == pytest.approx(0.5 * r["Re_full"])


def test_compute_design_auto_n():
    r = d.compute_design(_spec(turn_mode="auto"))
    assert r["n"] == pytest.approx(390.0 / 24.0)


def test_compute_design_invalid_raises():
    with pytest.raises(ValueError):
        d.compute_design(_spec(vin_min=0.0))