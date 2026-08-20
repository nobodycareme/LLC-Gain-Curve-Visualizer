# -*- coding: utf-8 -*-
"""Phase 1：数学边界问题回归（scalar/string 强转、find_peak isfinite、
make_fn_curve n>=2、高频极限、边界 overflow）。

对 EXE 实际使用的纯 Python 层 ``llc_py`` 与其 numpy 权威参考 ``llc_model``
同时断言，确保两条实现数值一致、边界行为一致。
"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_py  # noqa: E402
import llc_model  # noqa: E402

MODULES = [llc_py, llc_model]


# ---- 1) llc_gain 标量路径：q 以字符串传入必须与数值路径一致 ----
@pytest.mark.parametrize("mod", MODULES)
def test_gain_scalar_q_as_string(mod):
    fn, k, qv = 0.8, 5.0, "0.5"
    a = mod.llc_gain(fn, k, float(qv))
    b = mod.llc_gain(fn, k, qv)
    assert a == pytest.approx(b, rel=1e-12)
    assert isinstance(b, float)


@pytest.mark.parametrize("mod", MODULES)
def test_gain_scalar_matches_sequence(mod):
    fn, k, qv = 0.8, 5.0, 0.5
    seq = [mod.llc_gain(fn, k, qv) for fn in (0.8, 0.8)]
    scalar = mod.llc_gain(0.8, k, qv)
    assert float(seq[0]) == pytest.approx(scalar, rel=1e-12)


# ---- 2) find_peak 必须用 isfinite 排除 NaN 与 ±Inf ----
@pytest.mark.parametrize("mod", MODULES)
def test_find_peak_excludes_inf_and_nan(mod):
    fn_curve = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
    m_curve = [2.0, float("inf"), 3.5, float("nan"), 4.0, 5.0, 4.5]
    fpeak, mpeak = mod.find_peak(fn_curve, m_curve)
    # Inf(=m=5) 与 NaN 都被排除，正确峰值为 m=5.0 @ fn=0.9
    assert math.isfinite(fpeak) and math.isfinite(mpeak)
    assert fpeak == pytest.approx(0.9)
    assert mpeak == pytest.approx(5.0)


@pytest.mark.parametrize("mod", MODULES)
def test_find_peak_all_nonfinite_returns_nan(mod):
    fn_curve = [0.5, 0.6]
    m_curve = [float("nan"), float("inf")]
    fpeak, mpeak = mod.find_peak(fn_curve, m_curve)
    assert math.isnan(fpeak) and math.isnan(mpeak)


# ---- 3) make_fn_curve 要求 n >= 2 ----
@pytest.mark.parametrize("mod", MODULES)
def test_make_fn_curve_rejects_n_lt_2(mod):
    with pytest.raises(ValueError):
        mod.make_fn_curve(1)
    with pytest.raises(ValueError):
        mod.make_fn_curve(0)
    with pytest.raises(ValueError):
        mod.make_fn_curve(-3)


@pytest.mark.parametrize("mod", MODULES)
def test_make_fn_curve_n2_ok(mod):
    cur = mod.make_fn_curve(2)
    assert len(cur) == 2
    assert cur[0] < cur[1]


# ---- 4) 高频极限：Q>0 时 fn→∞ → M→0，不得误写成 K/(1+K) ----
@pytest.mark.parametrize("mod", MODULES)
def test_high_freq_limit_q_gt0_tends_zero(mod):
    k, q = 5.0, 0.5
    fns = (10.0, 100.0, 1e3, 1e6)
    ms = [float(mod.llc_gain(fn, k, q)) for fn in fns]
    # 单调递减且充分高频处趋零；绝不趋于有限常数 K/(1+K)=0.833
    assert all(ms[i] > ms[i + 1] for i in range(len(ms) - 1))
    assert ms[-2] < 3e-3     # fn=1e3
    assert ms[-1] < 5e-6     # fn=1e6
    assert all(m < k / (1.0 + k) * 0.5 for m in ms)


@pytest.mark.parametrize("mod", MODULES)
def test_high_freq_limit_q0_is_k_over_1plusk(mod):
    k = 5.0
    m_inf = float(mod.llc_gain(1e6, k, 0.0))
    assert m_inf == pytest.approx(k / (1.0 + k), rel=1e-3)


# ---- 5) 标量/序列两条路径的更多一致性（字符串 k 也可解析） ----
@pytest.mark.parametrize("mod", MODULES)
def test_gain_k_as_string_scalar(mod):
    m_num = mod.llc_gain(1.3, 5.0, 2.0)
    m_str = mod.llc_gain(1.3, "5", "2")
    assert m_num == pytest.approx(m_str, rel=1e-12)


# ---- 6) llc_py 与 llc_model 交叉一致（含边界函数） ----
def test_crosscheck_gain_and_boundary():
    import random

    rng = random.Random(1234)
    for _ in range(200):
        fn = 10.0 ** (rng.uniform(-1.0, 1.0))
        k = rng.uniform(1.5, 10.0)
        q = 10.0 ** (rng.uniform(-1.3, 1.0))
        m1 = float(llc_py.llc_gain(fn, k, q))
        m2 = float(llc_model.llc_gain(fn, k, q))
        assert m1 == pytest.approx(m2, rel=1e-9)
        fb1 = llc_py.boundary_frequency(k, q)
        fb2 = llc_model.boundary_frequency(k, q)
        assert fb1 == pytest.approx(fb2, rel=1e-9)


# ---- 7) 极端有限 K/Q 下 boundary_frequency 不 overflow、答案稳定 ----
@pytest.mark.parametrize("mod", MODULES)
@pytest.mark.parametrize("k,q,expected_band", [
    (1e7, 1e7, (2e-7, 1.0)),      # 极大 (K·Q)² 远超出双精度 A，(B,K+1−A) 分支处理
    (1e-6, 1e-6, (0.5, 1.0)),    # 极小 K·Q → fnb 接近 1/sqrt(1+K)≈1
    (1e6, 1e-9, (9e-4, 2e-3)),   # 极大 K、Q→0 → fnb≈1/sqrt(1+K)≈1e-3
])
def test_boundary_frequency_extreme_finite(mod, k, q, expected_band):
    fb = mod.boundary_frequency(k, q)
    lo, hi = expected_band
    assert math.isfinite(fb)
    assert lo <= fb <= hi