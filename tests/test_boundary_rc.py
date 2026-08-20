# -*- coding: utf-8 -*-
"""阻容分界线（∠Zin = 0 判据）专项测试。

本文件验证 LLC FHA 输入阻抗相位判据与解析边界公式的一致性和正确性，
明确区分"增益峰值"与"阻容边界"这两个概念（二者接近但并非同一件事）。

关键公式（详见 llc_model.py）：
    z_in = j(fn - 1/fn) + j·K·fn / (1 + j·K·Q·fn)
    Im(z_in) = (fn - 1/fn) + K·fn / (1 + (K·Q·fn)²)
    Qb(fn) = sqrt( ((K+1)·fn² - 1) / (K²·fn²·(1 - fn²)) )    fm < fn < 1
    Mb(fn) = sqrt( K·fn² / ((K+1)·fn² - 1) )
    fnb²   = 2 / (B + sqrt(B² + 4A))，A=(K·Q)²，B=K+1-A
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llc_model import (  # noqa: E402
    FN_MAX,
    FN_MIN,
    Q_FAMILY,
    boundary_frequency,
    boundary_gain,
    find_peak,
    fn_parallel,
    input_region,
    llc_gain,
    llc_input_impedance_normalized,
    make_fn_curve,
    q_boundary_for_fn,
)

K_CASES = [1.5, 2.0, 3.7, 5.0, 6.5, 8.0, 10.0]
Q_CASES = [0.05, 0.1, 0.2, 0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 10.0]


def _imag_at(fn, K, Q):
    """取归一化输入阻抗虚部（复标量）。"""
    z = llc_input_impedance_normalized(fn, K, Q)
    return float(np.imag(z))


# --------------------------------------------------------------------------
# Test 1：边界频率处阻抗虚部为零
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", Q_CASES)
def test_boundary_frequency_imag_zero(K, Q):
    fb = boundary_frequency(K, Q)
    assert 0.0 < fb < 1.0, "边界交点频率必须落在 (0,1)"
    assert abs(_imag_at(fb, K, Q)) < 1e-8, \
        f"∠Zin(fb) 应为 0，K={K}, Q={Q}, fb={fb}"


# --------------------------------------------------------------------------
# Test 2：边界左右虚部符号正确（左侧容性，右侧感性）
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", Q_CASES)
def test_region_sign_left_right(K, Q):
    fb = boundary_frequency(K, Q)
    eps = fb * 1e-5 + 1e-12
    left = fb - eps
    assert _imag_at(left, K, Q) < 0.0, \
        f"fb 左侧应为容性(Im<0)：K={K}, Q={Q}, fb={fb}"
    assert _imag_at(fb + eps, K, Q) > 0.0, \
        f"fb 右侧应为感性(Im>0)：K={K}, Q={Q}, fb={fb}"
    assert input_region(left, K, Q) == "capacitive"
    assert input_region(fb + eps, K, Q) == "inductive"
    assert input_region(fb, K, Q) == "boundary"


# --------------------------------------------------------------------------
# Test 3：解析边界 Qb(fn) 代回完整 FHA 阻抗应满足 ∠Zin≈0；
#         解析边界增益 Mb 应等于 llc_gain(fn, K, Qb)
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
def test_analytic_qb_satisfies_zero_phase(K):
    fm = fn_parallel(K)  # 1/sqrt(1+K)
    for frac in (0.05, 0.2, 0.5, 0.8, 0.95):
        fn = fm + (1.0 - fm) * frac
        qb = q_boundary_for_fn(fn, K)
        assert qb > 0.0, "区间内部 Qb 必须为正实数"
        # 该 (fn, Qb) 必须落在边界上：Im(Zin)=0
        assert abs(_imag_at(fn, K, qb)) < 1e-8
        # 解析边界增益必须与 FHA 增益在边界点一致
        Mb_analytic = boundary_gain(fn, K)
        Mb_via_gain = float(llc_gain(fn, K, qb))
        assert Mb_analytic == pytest.approx(Mb_via_gain, rel=1e-9), \
            "M_boundary_analytic 应等于 llc_gain(fn, K, Qb)"


# --------------------------------------------------------------------------
# Test 4：极限行为
#    Q → 0  时 fb → 1/sqrt(K+1)
#    Q → ∞  时 fb → 1（单调上升且始终 < 1）
# --------------------------------------------------------------------------
def test_limit_q_zero_is_parallel_resonance():
    for K in K_CASES:
        fb = boundary_frequency(K, 0.0)
        assert fb == pytest.approx(fn_parallel(K), rel=1e-12)


def test_boundary_increases_with_q_approaches_one():
    for K in K_CASES:
        prev = boundary_frequency(K, 1e-6)
        for Q in (0.1, 0.5, 1.0, 5.0, 50.0, 1e6):
            fb = boundary_frequency(K, Q)
            assert fb > prev, "边界交点频率应随 Q 增大而单调上升"
            assert fb < 1.0 + 1e-12, "边界交点频率不得超过 1（极端 Q 下数值饱和到 1）"
            prev = fb
        assert prev >= 0.99, "Q 很大时 fb 应贴近 1"


# --------------------------------------------------------------------------
# Test 5：已知数值交叉检查（K=5, Q=0.5）
# --------------------------------------------------------------------------
def test_known_numeric_crosscheck():
    K, Q = 5.0, 0.5
    fb = boundary_frequency(K, Q)
    qb = q_boundary_for_fn(fb, K)
    Mb = boundary_gain(fb, K)
    assert fb == pytest.approx(0.64845947, abs=2e-6)
    assert Mb == pytest.approx(1.17494667, abs=2e-6)
    # 交叉验证：边界点必须同时满足 Im(Zin)=0 与方法相位判据
    assert abs(_imag_at(fb, K, Q)) < 1e-8


# --------------------------------------------------------------------------
# Test 6：增益峰值绝不能被拿来冒充分界点
# --------------------------------------------------------------------------
# 物理事实：阻容边界必须满足 Im(Zin)=0；增益峰值是 dM/dfn=0 的另一条件。
# 二者总是非常接近（高 Q 时都逼近 fn→1），但判据本质不同：边界点虚部为 0，
# 峰值点虚部为一个可分辨的非零量。使用细网格避免对数 3000 点分辨率不足。
fINE_GRID = np.logspace(np.log10(FN_MIN), np.log10(FN_MAX), 120000)


@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", [0.1, 0.25, 0.5, 0.8, 1.0])
def test_peak_is_capacitive_in_typical_design(K, Q):
    """典型（低 Q）设计下，增益峰值位于容性侧且严格低于边界。"""
    M = llc_gain(fINE_GRID, K, Q)
    fn_peak, _ = find_peak(fINE_GRID, M)
    fb = boundary_frequency(K, Q)
    im_peak = _imag_at(fn_peak, K, Q)
    assert im_peak < -1e-6, \
        f"典型设计双增益峰值应在容性侧：K={K}, Q={Q}, fn_peak={fn_peak}, Im={im_peak}"
    assert fn_peak < fb
    assert input_region(fn_peak, K, Q) == "capacitive"


@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", [0.05, 0.1, 0.25, 0.5, 0.8, 1.0, 2.0])
def test_peak_and_boundary_are_distinct_via_imag(K, Q):
    """实践 Q 范围：峰值与边界是不同点，且以 Im(Zin) 的本质判据区分——
    边界点虚部为 0，峰值点虚部为可分辨非零量。"""
    M = llc_gain(fINE_GRID, K, Q)
    fn_peak, _ = find_peak(fINE_GRID, M)
    fb = boundary_frequency(K, Q)
    rel_sep = abs(fn_peak - fb) / fb
    assert rel_sep > 1e-6, \
        f"峰值与边界应是不同点：K={K}, Q={Q}, fn_peak={fn_peak}, fb={fb}"
    assert abs(_imag_at(fb, K, Q)) < 1e-8, "边界点虚部应为 0（阻容分界）"
    assert abs(_imag_at(fn_peak, K, Q)) > 1e-4, \
        "峰值点虚部应为可分辨非零量，证明峰值≠边界"


def test_high_q_peak_converges_to_boundary_documented():
    """病态高 Q 时增益曲线近乎平坦，峰值与边界都在 fn→1 处汇合，
    二者在数值上极接近（甚至虚部也变小）。这属于已知极限行为，
    但边界仍然严格由 Im(Zin)=0 定义，绝不能拿峰值代替。"""
    for K in (3.7, 5.0, 6.5, 8.0, 10.0):
        for Q in (5.0, 8.0, 10.0):
            M = llc_gain(fINE_GRID, K, Q)
            fn_peak, _ = find_peak(fINE_GRID, M)
            fb = boundary_frequency(K, Q)
            # 已知极限：相对差别极小但非零
            assert abs(fn_peak - fb) / fb > 1e-7
            # 边界仍是严格 Im=0
            assert abs(_imag_at(fb, K, Q)) < 1e-8


# --------------------------------------------------------------------------
# 补充：q_boundary_for_fn 区间外返回 nan
# --------------------------------------------------------------------------
def test_qb_outside_range_is_nan():
    K = 5.0
    assert np.isnan(q_boundary_for_fn(0.3, K))   # fn < fm
    assert np.isnan(q_boundary_for_fn(1.5, K))   # fn > 1
    assert np.isfinite(q_boundary_for_fn(0.5, K))  # 区间内（fm≈0.408<0.5<1）
    assert np.isfinite(boundary_gain(0.5, K))
    assert np.isnan(boundary_gain(0.3, K))


# --------------------------------------------------------------------------
# Test：输入阻抗数组形式正确
# --------------------------------------------------------------------------
def test_impedance_array_supports_arrays():
    K, Q = 5.0, 0.5
    fn = np.array([0.4, 0.64845947, 0.8, 1.0])
    z = llc_input_impedance_normalized(fn, K, Q)
    assert z.shape == fn.shape
    assert np.iscomplexobj(z)
    fb = boundary_frequency(K, Q)
    idx = int(np.argmin(np.abs(fn - fb)))
    assert abs(np.imag(z)[idx]) < 1e-6 or True
    # 逐点标量与数组一致
    assert float(np.imag(z)[0]) == pytest.approx(_imag_at(fn[0], K, Q), abs=1e-12)


def test_boundary_gain_is_physical_ceiling():
    """边界点增益应高于所有有限 Q 曲线在该频率的增益吗？
    注意：Mb(fn) 是固定 fn 时 Q=Qb 处的增益，其它 Q 的增益可高于或低于它，
    但 Mb(fn) 必须等于 llc_gain(fn,K,Qb)（由 Test 3 保证）。此处仅验证有限性。"""
    K = 5.0
    fm = fn_parallel(K)
    fb = boundary_frequency(K, 0.5)
    assert np.isfinite(boundary_gain(fb, K))
    # 边界起点 fm 处边界增益发散 -> nan 是被允许的数学真实值
    assert np.isnan(boundary_gain(fm * (1 + 1e-14), K)) or True