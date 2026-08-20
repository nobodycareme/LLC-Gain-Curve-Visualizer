# -*- coding: utf-8 -*-
"""boundary_frequency 单调性 + B≈0 连续性与分支正确性测试。

* **单调性**：固定 K，Q 增大时 fnb 单调不减，从 1/sqrt(1+K) 逼近 1。
  （允许机器精度下极大 Q 饱和为相同的 1.0，但不允许反向跳变。）
* **B≈0 支点连续性**：支点位于 ``Qc = sqrt(K+1)/K``（此时 B=K+1−A=0）。
  在两个分支（B>=0 / B<0）交界处必须**连续**、不跳变、精度损失可接受。
"""

from __future__ import annotations

import math
import os
import sys
from collections.abc import Iterable

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llc_model import boundary_frequency  # noqa: E402

K_CASES = [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 100.0]
Q_LOG = [0.0, 1e-12, 1e-9, 1e-6, 1e-3, 0.01, 0.1, 0.5, 1.0,
         10.0, 100.0, 1e4, 1e6, 1e8, 1e12]


def _qcrit(K: float) -> float:
    """B=K+1−A=0 的分支点 Q = sqrt(K+1)/K。"""
    return math.sqrt(K + 1.0) / K


@pytest.mark.parametrize("K", K_CASES)
def test_monotonic_non_decreasing_in_q(K):
    """固定 K：fnb(Q) 必须单调不减（可相等于机器极限，不得反向跳变）。"""
    prev = -1.0
    for Q in Q_LOG:
        fb = boundary_frequency(K, Q)
        assert fb >= prev - 1e-12, \
            f"单调性破坏：K={K}, Q={Q}, fb={fb} < prev={prev}"
        assert 0.0 < fb <= 1.0
        prev = fb


@pytest.mark.parametrize("K", K_CASES)
@pytest.mark.parametrize("Q", [1e4, 1e6, 1e8, 1e12])
def test_monotonic_toward_one_for_large_q(K, Q):
    """极大 Q 时 fnb 必须严格逼近 1（在可分辨范围内>较小 Q 的 fnb）。"""
    fb_small = boundary_frequency(K, 1.0)
    fb = boundary_frequency(K, Q)
    assert fb >= fb_small
    assert fb > 0.999 or fb == 1.0


# ---------------------------------------------------------------------------
# B≈0 支点两侧分支连续、不跳变
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
def test_branch_continuity_at_qcrit(K):
    """在 B=0 支点 Qc 两侧（±1e−12 相对）结果必须连续、接近支点本身。"""
    Qc = _qcrit(K)
    lo = boundary_frequency(K, Qc * (1.0 - 1e-12))
    mid = boundary_frequency(K, Qc)
    hi = boundary_frequency(K, Qc * (1.0 + 1e-12))
    # 三者彼此连续
    assert abs(lo - mid) <= 1e-9, f"B≈0 左支不连续：K={K}, lo={lo}, mid={mid}"
    assert abs(hi - mid) <= 1e-9, f"B≈0 右支不连续：K={K}, hi={hi}, mid={mid}"
    # 且都落在物理范围内
    assert all(0.0 < x <= 1.0 for x in (lo, mid, hi))


@pytest.mark.parametrize("K", K_CASES)
def test_branch_point_exact_analytic(K):
    """支点 Qc 处 B=0 → A x² − 1 = 0 → x = 1/sqrt(A) = 1/sqrt(K+1)，
    故 fnb = x^(1/2) = (K+1)^(−1/4)。"""
    Qc = _qcrit(K)
    fb = boundary_frequency(K, Qc)
    expected = (K + 1.0) ** -0.25
    assert fb == pytest.approx(expected, rel=1e-9), \
        f"支点解析值不符：K={K}, fb={fb}, expected={expected}"


# ---------------------------------------------------------------------------
# 全 K 全 Q 普适验证（覆盖 B>0、B≈0、B<0 三个区域）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("K", K_CASES)
def test_branches_cover_all_three_regions(K):
    """Q 扫描必须同时涉足 B>0、B≈0、B<0 三个区域，确保分支都被走通。"""
    Qc = _qcrit(K)
    small = boundary_frequency(K, Qc * 0.5)   # A<K+1 → B>0
    crit = boundary_frequency(K, Qc)          # A=K+1 → B≈0
    big = boundary_frequency(K, Qc * 2.0)     # A>K+1 → B<0
    assert small < crit < big, \
        f"三个区域应严格递增：K={K}, small={small}, crit={crit}, big={big}"


def test_does_not_raise_on_iterable_that_fails_crosscheck():
    """说明性：生产 API 只接受标量 K/Q，传序列属错误用法（不在本文件范围）。"""
    pass