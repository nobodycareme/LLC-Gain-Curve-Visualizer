# -*- coding: utf-8 -*-
"""LLC FHA 数学模型单元测试。

本文件遵循项目统一符号体系：
    K  = Lm / Lr                    励磁电感比
    fn = fs / fr                    归一化开关频率
    Q  = sqrt(Lr/Cr) / Rac          品质因数
    M(fn, K, Q)                      增益
"""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llc_model import (  # noqa: E402
    FN_MAX,
    FN_MIN,
    K_MAX,
    K_MIN,
    Q_FAMILY,
    find_peak,
    fn_parallel,
    fn_series,
    llc_gain,
    make_fn_curve,
    to_real_frequency,
)

K_CASES = [1.5, 2.0, 3.7, 5.0, 6.5, 8.0, 10.0]
Q_CASES = [0.05, 0.1, 0.2, 0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 10.0]


# --------------------------------------------------------------------------
# 1. M(fn=1) == 1 对任意合理 K、Q 成立
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", Q_CASES)
def test_gain_at_series_resonance_is_unity(K, Q):
    """fn=1 时增益恒为 1，与 Q、K 无关。"""
    M = llc_gain(1.0, K, Q)
    assert abs(float(M) - 1.0) < 1e-10


def test_gain_at_series_resonance_array_form():
    """数组形式下 fn=1 处同样等于 1。"""
    fn = np.array([1.0, 1.0, 1.0])
    M = llc_gain(fn, 5.0, 0.4531)
    assert np.allclose(M, 1.0, atol=1e-12)


# --------------------------------------------------------------------------
# 2. K = 5 时 fnp = 1/sqrt(1+K) = 1/sqrt(6)；fnr = 1
# --------------------------------------------------------------------------
def test_parallel_resonance_K5():
    assert abs(fn_parallel(5.0) - 1.0 / math.sqrt(6.0)) < 1e-12


@pytest.mark.parametrize("K", K_CASES)
def test_parallel_resonance_general(K):
    assert abs(fn_parallel(K) - 1.0 / math.sqrt(1.0 + K)) < 1e-12


def test_series_resonance_is_one():
    assert fn_series() == 1.0


# --------------------------------------------------------------------------
# 3. 数组输入正确计算
# --------------------------------------------------------------------------
def test_array_input_shape_and_elementwise():
    fn = make_fn_curve()
    M = llc_gain(fn, 5.0, 0.5)
    assert isinstance(M, np.ndarray)
    assert M.shape == fn.shape
    # 抽样比对：数组结果应与逐点标量计算一致
    for idx in (0, 7, 123, 1500, 2999):
        assert abs(M[idx] - float(llc_gain(fn[idx], 5.0, 0.5))) < 1e-12


def test_fn_curve_range_and_monotonic():
    fn = make_fn_curve()
    assert len(fn) == 3000
    assert abs(fn[0] - FN_MIN) < 1e-12
    assert abs(fn[-1] - FN_MAX) < 1e-12
    assert np.all(np.diff(fn) > 0)


# --------------------------------------------------------------------------
# 4. 合理参数下不应出现复数 / NaN / Inf
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", Q_CASES)
def test_no_complex_no_nan_no_inf(K, Q):
    fn = make_fn_curve()
    M = llc_gain(fn, K, Q)
    assert not np.iscomplexobj(M), "增益不应为复数"
    assert np.all(np.isfinite(M)), "增益不应出现 NaN 或 Inf"
    assert np.all(M >= 0.0), "增益不应为负"


def test_gain_is_positive_real_scalar():
    M = llc_gain(0.37, 5.0, 0.5)
    assert np.isrealobj(M)
    assert float(M) > 0.0


# --------------------------------------------------------------------------
# 5. 峰值搜索结果必须落在 fn 扫描范围内
# --------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", Q_CASES)
def test_peak_within_scan_range(K, Q):
    fn = make_fn_curve()
    M = llc_gain(fn, K, Q)
    fn_peak, Mpeak = find_peak(fn, M)
    assert FN_MIN <= fn_peak <= FN_MAX
    assert np.isfinite(Mpeak)
    assert Mpeak >= float(np.max(M)) - 1e-12


def test_peak_is_actual_maximum():
    fn = make_fn_curve()
    M = llc_gain(fn, 5.0, 0.2)
    fn_peak, Mpeak = find_peak(fn, M)
    assert abs(Mpeak - float(np.max(M))) < 1e-12
    assert abs(fn_peak - float(fn[int(np.argmax(M))])) < 1e-12


def test_peak_all_nan_returns_nan():
    fn = make_fn_curve()
    M = np.full_like(fn, np.nan)
    fn_peak, Mpeak = find_peak(fn, M)
    assert math.isnan(fn_peak) and math.isnan(Mpeak)


# --------------------------------------------------------------------------
# 6. 实际频率换算正确：fs=fn·fr，fp=fnp·fr，fpeak=fn_peak·fr
# --------------------------------------------------------------------------
def test_real_frequency_scalar():
    assert abs(to_real_frequency(1.0, 124.4) - 124.4) < 1e-12
    assert abs(to_real_frequency(2.0, 124.4) - 248.8) < 1e-12


def test_real_frequency_parallel_point():
    K = 5.0
    fr = 124.4
    fp = to_real_frequency(fn_parallel(K), fr)
    assert abs(fp - fr / math.sqrt(6.0)) < 1e-10


def test_real_frequency_array():
    fn = np.array([0.5, 1.0, 2.0])
    f = to_real_frequency(fn, 100.0)
    assert np.allclose(f, [50.0, 100.0, 200.0])


# --------------------------------------------------------------------------
# 7. 物理特性回归：低于 fnp 增益应趋于小，Q 越大峰值越低，
#    K 越大某个固定 fn 下增益行为符合 FHA 特性
# --------------------------------------------------------------------------
def test_peak_gain_decreases_with_q():
    fn = make_fn_curve()
    peaks = []
    for Q in (0.2, 0.5, 1.0, 2.0, 5.0):
        _, Mpeak = find_peak(fn, llc_gain(fn, 5.0, Q))
        peaks.append(Mpeak)
    assert all(peaks[i] > peaks[i + 1] for i in range(len(peaks) - 1)), \
        "Q 增大时峰值增益应单调下降"


def test_gain_family_all_computable():
    fn = make_fn_curve()
    for Q in Q_FAMILY:
        M = llc_gain(fn, 5.0, Q)
        assert np.all(np.isfinite(M))


def test_high_frequency_asymptote():
    """fn 远大于 1 时增益应趋近于 K/(1+K) 以下，且随 fn 增大而下降。"""
    K = 5.0
    M_large = float(llc_gain(10.0, K, 0.5))
    M_larger = float(llc_gain(9.0, K, 0.5))
    assert M_large < M_larger
    # 渐近极限：fn→+inf 时 M→K/(1+K) = 5/6
    assert M_large < 5.0 / 6.0


def test_K_increases_asymptotic_gain():
    """K 越大，高频渐近增益 K/(1+K) 越大（所有参考曲线一起变化）。"""
    M_K5 = float(llc_gain(10.0, 5.0, 1.0))
    M_K10 = float(llc_gain(10.0, 10.0, 1.0))
    assert M_K5 < M_K10


# --------------------------------------------------------------------------
# 8. 典型数值回归条件：K=5, Q=0.5, fr=124.4 kHz
# --------------------------------------------------------------------------
def test_numeric_regression_defaults():
    K = 5.0
    Q = 0.5
    fr = 124.4
    # fnp = 1/sqrt(1+K)
    fnp = fn_parallel(K)
    assert abs(fnp - 0.408248290463863) < 1e-9
    # fs = fn*fr = 1*fr
    assert abs(to_real_frequency(1.0, fr) - 124.4) < 1e-9
    # fp = fnp*fr
    assert abs(to_real_frequency(fnp, fr) - fnp * fr) < 1e-9
    # M(fn=1)=1
    assert abs(float(llc_gain(1.0, K, Q)) - 1.0) < 1e-10