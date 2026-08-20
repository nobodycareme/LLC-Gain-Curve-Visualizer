# -*- coding: utf-8 -*-
"""TI SLUP263 固定设计案例回归。

参考：Texas Instruments ``Designing an LLC Resonant Half-Bridge Power Converter``
（Hong Huang, SLUP263）。本项目把它作为工程设计层端的固定回归锚点。

采用"实际采用参数"（Lr=60µH、Lm=210µH、Cr=27.3nF）验证：
    Re_full、Q_full、Q_overload、M_req、fr_actual、fn_min/fn_max、fs_min/fs_max，
以及在低输入过载最劣工况下的 FHA 电流、次级电流与 Cr 应力。

由于 TI 文档中的参考值为取整后的工程值，允许合理误差；本测试强调
**物理关系、量级与趋势必须一致**（并同时做紧一点的数值级断言）。
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_design as d  # noqa: E402
import llc_solver as sol  # noqa: E402
import llc_stress as st  # noqa: E402


# -- 设计规格（SLUP263 参考案例的输入）--
BRIDGE = "half"
RECT = "ct_diode"
VIN_MIN, VIN_NOM, VIN_MAX = 300.0, 390.0, 400.0
VO = 12.0
POUT = 300.0
OVERLOAD = 1.1
N = 16.0
FR_ACTUAL = 124.4e3
LR_ACT = 60e-6
LM_ACT = 210e-6
CR_ACT = 27.3e-9

# -- TI 参考值（允许合理取整误差）--
REF = {
    "Re_full": 99.7,
    "M_req_max": 1.30,
    "M_req_min": 0.99,
    "fr_actual_khz": 124.4,
    "Q_full": 0.47,
    "Q_overload": 0.52,
    "fn_min": 0.65,
    "fn_max": 1.02,
    "fs_min_khz": 80.7,
    "fs_max_khz": 126.9,
    "Ioe": 1.91, "Im": 1.63, "Ir": 2.51,
    "sec_total": 30.6, "ct_half_rms": 21.6, "ct_half_avg": 13.8,
    "vcr_ac_rms": 187.9, "vcr_rms": 276.0, "vcr_peak": 467.0,
}


def _tank():
    return d.back_calc_actual(LR_ACT, CR_ACT, LM_ACT)


def _spec():
    return d.DesignSpec(
        bridge=BRIDGE, rect=RECT, vin_min=VIN_MIN, vin_nom=VIN_NOM,
        vin_max=VIN_MAX, vo=VO, pout=POUT, vdrop=0.0, efficiency=1.0,
        overload=OVERLOAD, turn_mode="manual", n_manual=N,
        fr_hz=FR_ACTUAL, k=LM_ACT / LR_ACT, q_selected=REF["Q_full"],
    )


# ---- 1) 设计端：Re/M_req/Q/fr_actual ----
def test_re_full_matches():
    r = d.compute_design(_spec())
    assert r["Re_full"] == pytest.approx(REF["Re_full"], rel=0.02)


def test_m_required_matches():
    r = d.compute_design(_spec())
    assert r["M_req_max"] == pytest.approx(REF["M_req_max"], rel=0.02)
    assert r["M_req_min"] == pytest.approx(REF["M_req_min"], rel=0.06)


def test_fr_actual_matches():
    t = _tank()
    assert t["fr"] / 1e3 == pytest.approx(REF["fr_actual_khz"], rel=0.02)


# ---- 2) 满载/过载 Q ----
def test_q_full_and_overload():
    t = _tank()                       # 实际采用参数反算的 Zr
    r = d.compute_design(_spec())
    # 用实际谐振腔 Zr 计算满载/过载 Q
    q_full = t["Zr"] / r["Re_full"]
    q_overload = t["Zr"] / r["Re_overload"]
    assert q_full == pytest.approx(REF["Q_full"], rel=0.05)
    assert q_overload == pytest.approx(REF["Q_overload"], rel=0.05)
    # 理论计算谐振腔保持"Zr = Q_selected·Re_full"
    assert r["Zr_calc"] == pytest.approx(r["Q_selected"] * r["Re_full"])


# ---- 3) fn_min / fn_max（真求解）+ 感知区约束 ----
def test_frequency_roots_match_and_feasible():
    r = d.compute_design(_spec())
    s = sol.solve_gain_frequency(
        k=LM_ACT / LR_ACT,
        q_min_branch=r["Q_overload"], m_req_max=r["M_req_max"],
        q_max_branch=r["Q_full"], m_req_min=r["M_req_min"],
    )
    assert s["fn_min_feasible"], s["fn_min_reason"]
    assert s["fn_max_feasible"]
    assert s["fn_min"] == pytest.approx(REF["fn_min"], rel=0.06)
    assert s["fn_max"] == pytest.approx(REF["fn_max"], rel=0.06)
    # 感知侧 / 单调性
    assert s["fn_min"] >= s["fn_boundary"]
    assert s["fn_min"] <= s["fn_max"]
    assert s["fn_min"] * FR_ACTUAL / 1e3 == pytest.approx(
        REF["fs_min_khz"], rel=0.06)
    assert s["fn_max"] * FR_ACTUAL / 1e3 == pytest.approx(
        REF["fs_max_khz"], rel=0.06)


# ---- 4) 最劣工况 FHA 电流（低输入过载：Vin_min + Q_overload @ fn_min）----
def test_worst_case_currents():
    f = d.back_calc_actual(LR_ACT, CR_ACT, LM_ACT)
    r = d.compute_design(_spec())
    s = sol.solve_fn_min(
        k=LM_ACT / LR_ACT, q=r["Q_overload"], m_req_max=r["M_req_max"])
    fs_hz = s["fn"] * f["fr"]
    # 低输入过载：使用过载 Re 与最高输入电流的工况
    p = st.fha_phasor(VIN_MIN, fs_hz, LR_ACT, LM_ACT, CR_ACT,
                      r["Re_overload"], BRIDGE)
    assert p["kcl_ok"]
    assert p["ir_rms"] == pytest.approx(REF["Ir"], rel=0.10)
    assert p["ioe_rms"] == pytest.approx(REF["Ioe"], rel=0.10)
    assert p["im_rms"] == pytest.approx(REF["Im"], rel=0.10)
    # 趋势：励磁 < 谐振原边；三者 Ir ≈ Ioe + Im
    assert p["im_rms"] < p["ir_rms"]
    assert p["ioe_rms"] < p["ir_rms"]


# ---- 5) 次级电流（中心抽头，拓扑专用公式）----
def test_secondary_currents():
    r = d.compute_design(_spec())
    io_dc = r["Pout_overload"] / VO
    sec = st.secondary_currents("ct_diode", REF["Ioe"], N, io_dc)
    assert sec["total_secondary_rms"] == pytest.approx(REF["sec_total"], rel=0.10)
    assert sec["ct_half_rms"] == pytest.approx(REF["ct_half_rms"], rel=0.05)
    assert sec["ct_half_avg"] == pytest.approx(REF["ct_half_avg"], rel=0.05)


# ---- 6) Cr 应力（在标称输入 + 最低频率的"近最劣"工作点评估）----
def test_cr_stress_order():
    f = d.back_calc_actual(LR_ACT, CR_ACT, LM_ACT)
    r = d.compute_design(_spec())
    s = sol.solve_fn_min(k=LM_ACT / LR_ACT, q=r["Q_overload"],
                         m_req_max=r["M_req_max"])
    fs_hz = s["fn"] * f["fr"]
    p = st.fha_phasor(VIN_NOM, fs_hz, LR_ACT, LM_ACT, CR_ACT,
                      r["Re_overload"], BRIDGE)
    c = st.cr_stress(p["ir_rms"], p["omega"], CR_ACT, VIN_NOM, BRIDGE)
    # 量级 + 关系
    assert c["vcr_ac_rms"] == pytest.approx(REF["vcr_ac_rms"], rel=0.20)
    assert c["vcr_rms"] == pytest.approx(REF["vcr_rms"], rel=0.20)
    assert c["vcr_peak"] == pytest.approx(REF["vcr_peak"], rel=0.20)
    assert c["vcr_rms"] > c["vcr_ac_rms"]
    assert c["vcr_peak"] > c["vcr_rms"]
    # Vpeak 严格 = Vdc + √2·Vac，绝非 Vin/2
    assert c["vcr_peak"] == pytest.approx(
        VIN_NOM / 2.0 + math.sqrt(2) * c["vcr_ac_rms"], rel=1e-9)
    assert c["vcr_peak"] > VIN_NOM / 2.0


# ---- 7) 物理量纲一致性（不依赖具体取值）----
def test_relations_invariant():
    t = _tank()
    r = d.compute_design(_spec())
    # Re_overload = Re_full/OL
    assert r["Re_overload"] == pytest.approx(r["Re_full"] / OVERLOAD)
    # Q_full·Re_full == Q_overload·Re_overload == Zr
    assert r["Q_full"] * r["Re_full"] == pytest.approx(r["Zr_calc"])
    assert r["Q_overload"] * r["Re_overload"] == pytest.approx(r["Zr_calc"], rel=1e-6)
    # Lm = K·Lr
    assert t["K"] == pytest.approx(LM_ACT / LR_ACT)