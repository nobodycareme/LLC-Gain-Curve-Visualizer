# -*- coding: utf-8 -*-
"""llc_solver（fn_min/fn_max 数值求根）单元测试。"""

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import llc_solver as sol  # noqa: E402
from llc_py import boundary_frequency, llc_gain  # noqa: E402


def _rel(fn, k, q, m_target):
    """检查根：|M(fn)-target| 足够小"""
    return abs(float(llc_gain(fn, k, q)) - m_target)


# ---- fn_min 是真实求解（非采样 3000 点近似）----
def test_fn_min_is_true_root():
    k, q, mreq = 3.5, 0.52, 1.30
    r = sol.solve_fn_min(k, q, mreq)
    assert r["feasible"]
    fn = r["fn"]
    # 真正的根：增益在该频率处命中目标
    assert _rel(fn, k, q, mreq) < 1e-8
    # 位于感性工作侧：fn_min >= fn_boundary
    assert fn >= r["fn_boundary"] - 1e-9
    assert fn <= 1.0


def test_fn_max_is_true_root():
    k, q, mreq = 3.5, 0.47, 0.975
    r = sol.solve_fn_max(k, q, mreq)
    fn = r["fn"]
    assert _rel(fn, k, q, mreq) < 1e-8
    assert fn >= 1.0


# ---- 增益能力不足判定 ----
def test_fn_min_infeasible_when_gain_insufficient():
    k, q = 3.5, 0.52
    m_boundary = float(llc_gain(boundary_frequency(k, q), k, q))
    r = sol.solve_fn_min(k, q, m_boundary * 1.05)   # 超过能力
    assert not r["feasible"]
    assert r["reason"]
    assert math.isnan(r["fn"])


def test_fn_min_feasible_at_boundary():
    k, q = 3.5, 0.52
    m_boundary = float(llc_gain(boundary_frequency(k, q), k, q))
    r = sol.solve_fn_min(k, q, m_boundary)          # 恰好等于能力
    assert r["feasible"]
    assert r["fn"] <= boundary_frequency(k, q) + 1e-6 or \
        _rel(r["fn"], k, q, m_boundary) < 1e-6


# ---- 不同 Q 支路 ----
def test_fn_min_and_max_different_q_branches():
    r = sol.solve_gain_frequency(k=3.5,
                                 q_min_branch=0.52, m_req_max=1.30,
                                 q_max_branch=0.47, m_req_min=0.975)
    assert r["fn_min_feasible"]
    assert r["fn_max_feasible"]
    assert r["fn_min"] <= r["fn_max"]
    assert r["fn_range_ok"]


# ---- 边界条件 ----
def test_fn_max_saturates_at_1_when_req_high():
    r = sol.solve_fn_max(3.5, 0.47, 1.5)
    assert r["fn"] == pytest.approx(1.0)


def test_fn_min_saturates_at_1_when_req_low():
    r = sol.solve_fn_min(3.5, 0.52, 0.95)
    assert r["fn"] == pytest.approx(1.0)


def test_string_q_coercion():
    r = sol.solve_fn_min(3.5, "0.52", 1.30)
    assert r["feasible"]


@pytest.mark.parametrize("q", (100.0, 0.01, 5.0))
def test_fn_min_various_q_finite_and_sane(q):
    r = sol.solve_fn_min(3.5, q, 1.30)
    if r["feasible"]:
        assert math.isfinite(r["fn"])
        assert r["fn"] <= 1.0 + 1e-9