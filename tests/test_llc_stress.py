# -*- coding: utf-8 -*-
"""llc_stress（FHA 相量/次级电流/Cr 应力）单元测试。"""

import cmath
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_stress as st  # noqa: E402


def test_fundamental_rms():
    assert st.half_bridge_fundamental_rms(390.0) == pytest.approx(
        math.sqrt(2) / math.pi * 390.0)
    assert st.full_bridge_fundamental_rms(390.0) == pytest.approx(
        2 * math.sqrt(2) / math.pi * 390.0)


def test_fha_phasor_kcl_and_rms():
    lr, lm, cr, re = 60e-6, 210e-6, 27.3e-9, 90.16
    p = st.fha_phasor(390.0, 80.7e3, lr, lm, cr, re, "half")
    assert p["kcl_ok"]                       # Ir ≈ Ioe + Im
    assert p["ir_rms"] > 0.0
    assert p["ioe_rms"] > 0.0 and p["im_rms"] > 0.0
    # Ir 峰值 = RMS × √2
    assert p["ir_peak"] == pytest.approx(p["ir_rms"] * math.sqrt(2), rel=1e-9)


def test_fha_phasor_impedance_chain():
    # 手动复数校验 Zin 链
    w = 2 * math.pi * 80.7e3
    Lr, Lm, Cr, Re = 60e-6, 210e-6, 27.3e-9, 90.16
    zs = 1j * w * Lr + 1 / (1j * w * Cr)
    zm = 1j * w * Lm
    zp = (zm * Re) / (zm + Re)
    zin = zs + zp
    p = st.fha_phasor(390.0, 80.7e3, Lr, Lm, Cr, Re, "half")
    assert p["Zin"] == pytest.approx(zin, rel=1e-9)
    vge = math.sqrt(2) / math.pi * 390.0
    ir_expect = vge / zin
    assert p["ir"] == pytest.approx(ir_expect, rel=1e-9)


def test_full_bridge_higher_vge():
    p_half = st.fha_phasor(390.0, 100e3, 60e-6, 210e-6, 27.3e-9, 90.16, "half")
    p_full = st.fha_phasor(390.0, 100e3, 60e-6, 210e-6, 27.3e-9, 90.16, "full")
    assert p_full["vge_rms"] == pytest.approx(2 * p_half["vge_rms"], rel=1e-9)


# ---- 次级电流（拓扑分离）----
def test_secondary_currents_center_tap():
    sec = st.secondary_currents("ct_diode", 1.91, 16.0, 27.5)
    assert sec["total_secondary_rms"] == pytest.approx(16.0 * 1.91)
    assert sec["ct_half_rms"] == pytest.approx(math.pi / 4.0 * 27.5)
    assert sec["ct_half_avg"] == pytest.approx(27.5 / 2.0)
    assert sec["fb_winding_rms"] is None


def test_secondary_currents_full_bridge_differs():
    # 全桥整流：单绕组全波 RMS，不等同于 CT 半绕组结果
    sec = st.secondary_currents("fb_diode", 1.91, 16.0, 27.5)
    fb_rms = sec["fb_winding_rms"]
    assert fb_rms is not None
    assert fb_rms == pytest.approx(math.pi / (2 * math.sqrt(2)) * 27.5)
    # 明确禁止套用 CT 的 π/4·Io
    assert fb_rms != pytest.approx(math.pi / 4.0 * 27.5)
    assert sec["ct_half_rms"] is None


# ---- Cr 应力 ----
def test_cr_stress_half_bridge():
    ir_rms, w, cr, vin = 2.5, 2 * math.pi * 80.7e3, 27.3e-9, 390.0
    c = st.cr_stress(ir_rms, w, cr, vin, "half")
    assert c["icr_rms"] == pytest.approx(ir_rms)
    assert c["icr_peak"] == pytest.approx(ir_rms * math.sqrt(2), rel=1e-9)
    vac = ir_rms / (w * cr)
    assert c["vcr_ac_rms"] == pytest.approx(vac)
    assert c["vcr_dc"] == pytest.approx(vin / 2.0)
    # Vrms = sqrt(Vdc² + Vac²)；Vpeak = Vdc + √2·Vac
    assert c["vcr_rms"] == pytest.approx(math.hypot(vin / 2.0, vac))
    assert c["vcr_peak"] == pytest.approx(vin / 2.0 + math.sqrt(2) * vac)
    # 严禁把峰值写成 Vin/2
    assert c["vcr_peak"] > vin / 2.0


def test_cr_stress_full_bridge_no_dc_bias():
    c = st.cr_stress(2.5, 2 * math.pi * 80.7e3, 27.3e-9, 390.0, "full")
    assert c["vcr_dc"] == pytest.approx(0.0)
    assert c["vcr_rms"] == pytest.approx(c["vcr_ac_rms"])


def test_phasor_magnitude():
    assert st.phasor_magnitude(3 + 4j) == pytest.approx(5.0)


@pytest.mark.parametrize("bridge", ("bad", "", None))
def test_unknown_bridge_raises(bridge):
    with pytest.raises(ValueError):
        st.fha_phasor(390.0, 100e3, 60e-6, 210e-6, 27.3e-9, 90.16, bridge)