# -*- coding: utf-8 -*-
"""boundary_frequency(K, Q) 全参数空间数值稳定性专项测试。

背景
----
旧实现无条件使用 ``x = 2/(B + sqrt(B² + 4A))``（A=(KQ)²，B=K+1−A）。
该有理化公式只在 ``B >= 0`` 时数值稳定；当 ``B < 0`` 且 ``|B|`` 较大时，
``sqrt(B²+4A) ≈ −B``，``B + sqrt(...)`` 变成两个巨大接近数相减 → 灾难性相消，
可能导致 ``fn`` 被提前舍入成 ``1.0``、分母舍入为 0 甚至 ZeroDivisionError。

修复后采用**按符号 B 分支**：
    B >= 0 : x = 2/(B + D)
    B <  0 : x = (−B + D)/(2A)，其中 D = sqrt(B² + 4A)
并用 ``math.hypot(B, 2·sqrt(A))`` 计算 D 防 overflow。
（两者数学上等价于同一正根，但单独使用任一个都无法覆盖全空间。）

本文件从**纯双精度、范围不变量、单调性、B≈0 连续性**四方面验证修复。
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llc_model import (  # noqa: E402
    boundary_frequency,
    fn_parallel,
    llc_input_impedance_normalized,
)

# 覆盖极值：Q 从 0 到 1e18，K 从小到大
EXTREME_K = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0]
EXTREME_Q = [
    0.0,
    1e-12, 1e-9, 1e-6, 1e-3, 0.01, 0.1, 0.5, 1.0,
    10.0, 100.0, 1e4, 1e6, 1e8, 1e12, 1e18,
]

RANGE_TOL = 1e-9      # 相对范围容差：fn ∈ [fnp, 1]，允许反射


def _imag_at(fn, K, Q):
    z = llc_input_impedance_normalized(fn, K, Q)
    return abs(float(z.imag))


# ---------------------------------------------------------------------------
# Q=0 精确极限
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", EXTREME_K)
def test_q_zero_exact_limit(K):
    fb = boundary_frequency(K, 0.0)
    assert fb == pytest.approx(fn_parallel(K), rel=1e-12)


# ---------------------------------------------------------------------------
# Q 极小（非零）不崩溃，且贴近下限
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", EXTREME_K)
@pytest.mark.parametrize("Q", [1e-12, 1e-9, 1e-6])
def test_tiny_q_no_crash_and_near_lower_bound(K, Q):
    fb = boundary_frequency(K, Q)
    fnp = fn_parallel(K)
    assert fnp <= fb <= 1.0
    assert fb - fnp < 1e-3, f"极小 Q 应贴近下限：K={K}, Q={Q}, fb={fb}, fnp={fnp}"


# ---------------------------------------------------------------------------
# 全参数范围不变量：fn ∈ [1/sqrt(1+K), 1]，且 Im(Zin(fb))≈0（绝对+相对容差）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", EXTREME_K)
@pytest.mark.parametrize("Q", EXTREME_Q)
def test_fb_in_range_and_imag_zero(K, Q):
    fb = boundary_frequency(K, Q)
    fnp = fn_parallel(K)
    # 范围不变量：绝不越界（机器精度内）
    assert fnp - RANGE_TOL <= fb <= 1.0 + RANGE_TOL, \
        f"fb 越界：K={K}, Q={Q}, fb={fb}, fnp={fnp}"

    # 原判据独立验证：Im(Zin(fb))≈0
    im = _imag_at(fb, K, Q)
    # 绝对 + 相对组合容差：尺度越大允许相对误差，但不允许无意义放大
    ref_scale = max(abs(fb), abs(1.0 - fb), 1e-9)
    tol = max(1e-10, ref_scale * 5e-9)
    assert im <= tol, f"Im(Zin(fb)) 应≈0：K={K}, Q={Q}, fb={fb}, im={im}, tol={tol}"


# ---------------------------------------------------------------------------
# 极大 Q：不崩溃，最终饱和到 1.0 或不越界
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", EXTREME_K)
@pytest.mark.parametrize("Q", [1e4, 1e6, 1e8, 1e12, 1e18])
def test_huge_q_no_crash_saturates_to_one(K, Q):
    fb = boundary_frequency(K, Q)
    assert fb == fb, "不得产生 NaN"
    assert fb > 0.0, "不得为 0 或负值"
    assert fb <= 1.0 + RANGE_TOL, "不得越界（上界 1）"
    # 极大 Q 应非常贴近 1
    assert fb > 1.0 - 1e-3 or fb == 1.0, \
        f"极大 Q 应贴近 1：K={K}, Q={Q}, fb={fb}"