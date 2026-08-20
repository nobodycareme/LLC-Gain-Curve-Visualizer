# -*- coding: utf-8 -*-
"""LLC FHA 数值求解层（纯 Python，无第三方依赖）。

负责真正求解 FHA 增益方程 ``M(fn, K, Q) = M_required`` 在指定带的根：

* ``fn_min``：低输入 + 最大增益需求 ``M_req_max``，在**感性工作侧** ``[fn_boundary, 1]``
  求解，且必须满足 ``fn_min >= fn_boundary``。若 ``M_req_max > M(fn_boundary)`` 则明确
  判定 **增益能力不足 / 设计不可行**。
* ``fn_max``：高输入 + 最小增益需求 ``M_req_min``，在 ``[1, +∞)`` 求解。

**严禁**用不含 Q 的空载解析式近似；**严禁**只靠采样 3000 个点找最近点。
根采用可靠的二分法（bisection，收敛保证、无需 SciPy），对单调分支必有唯一根。
"""

from __future__ import annotations

import math

__all__ = [
    "solve_gain_frequency",
    "solve_fn_min",
    "solve_fn_max",
    "FACTOR_SQRT2",
    "OPTIMISM_LIMIT",
]

#: fn_max 上界逐级外推的倍增因子；M→0 需要很高频率时用指数上界定位
FACTOR_SQRT2 = math.sqrt(2.0)
#: fn 允许的最大搜索上限（防御性护栏）
OPTIMISM_LIMIT = 1e5

from llc_py import boundary_frequency, llc_gain  # noqa: E402


def _f_bisect(f, a: float, b: float, fa: float, fb: float,
              xtol: float = 1e-10, max_iter: int = 200) -> float:
    """在 ``[a,b]`` 内对单调连续函数求根。``f(a)`` 与 ``f(b)`` 必须异号。

    ``f`` 在 ``[a,b]`` 上随参数**单调递减**均可用（内部按异号二分，不要求方向）。
    """
    if fa * fb > 0.0:
        raise ValueError("二分法输入未构成异号括号")
    if fa == 0.0:
        return float(a)
    if fb == 0.0:
        return float(b)
    for _ in range(max_iter):
        mid = 0.5 * (a + b)
        if b - a < xtol:
            return mid
        fm = f(mid)
        if fm == 0.0:
            return mid
        if fa * fm < 0.0:
            b, fb = mid, fm
        else:
            a, fa = mid, fm
    return 0.5 * (a + b)


def _upper_bound_for_low_gain(k: float, q: float, m_target: float,
                              start: float = 1.0) -> float:
    """外推得到使 ``M(fn) < m_target`` 的 fn 上界（M 在 [1,∞) 单调递减 → M→0）。"""
    hi = float(start)
    for _ in range(60):
        if llc_gain(hi, k, q) < m_target:
            if hi > OPTIMISM_LIMIT:
                return OPTIMISM_LIMIT
            return hi
        hi = hi * 10.0
    return OPTIMISM_LIMIT


def solve_fn_min(k: float, q: float, m_req_max: float) -> dict:
    """求解最低工作频率 ``fn_min``（感性侧，最大增益工况）。

    返回 dict：
        ``fn``：求得的 fn_min；
        ``feasible``：是否可行；
        ``reason``：不可行时的中文原因（可行时为 ``""``）；
        ``fn_boundary``、``M_boundary``：该 Q 曲线阻容边界交点与其增益。
    """
    k = float(k)
    q = float(q)
    m_req_max = float(m_req_max)
    if m_req_max <= 0.0 or k <= 0.0:
        raise ValueError("K 与 M_req_max 必须 > 0")

    fn_b = float(boundary_frequency(k, q))
    m_b = float(llc_gain(fn_b, k, q))  # 感性侧可取得的最大增益能力

    # 增益能力不足
    if m_req_max > m_b * (1.0 + 1e-12):
        return {
            "fn": float("nan"), "feasible": False,
            "reason": "增益能力不足：M_req_max 超过该 Q 曲线在阻容边界处的增益 M_boundary",
            "fn_boundary": fn_b, "M_boundary": m_b,
        }
    # 需求增益 ≤1：串联谐振点已满足，无需降到 1 以下
    if m_req_max <= 1.0 + 1e-12:
        return {
            "fn": 1.0, "feasible": True, "reason": "",
            "fn_boundary": fn_b, "M_boundary": m_b,
        }

    # M(fn) 在 [fn_b, 1] 单调递减：f(fn_b)>0（可取得更大增益），f(1)=1-M_req_max<0
    def f(x):
        return float(llc_gain(x, k, q)) - m_req_max

    a, b = fn_b, 1.0
    fa, fb = f(a), f(b)
    try:
        fn = _f_bisect(f, a, b, fa, fb)
    except ValueError:  # 理论不该发生（上面已保证异号），兜底
        fn = fn_b
    # 保证位于感性工作侧
    if fn < fn_b:
        fn = fn_b
    return {"fn": fn, "feasible": True, "reason": "",
            "fn_boundary": fn_b, "M_boundary": m_b}


def solve_fn_max(k: float, q: float, m_req_min: float) -> dict:
    """求解最高工作频率 ``fn_max``（高输入、低增益工况）。

    ``fn_max`` 在 ``[1, +∞)`` 上求解 ``M(fn) = m_req_min``；M 从 1 单调递减到 0。
    """
    k = float(k)
    q = float(q)
    m_req_min = float(m_req_min)
    if m_req_min <= 0.0 or k <= 0.0:
        raise ValueError("K 与 M_req_min 必须 > 0")

    if m_req_min >= 1.0 - 1e-12:
        return {"fn": 1.0, "feasible": True, "reason": ""}

    def f(x):
        return float(llc_gain(x, k, q)) - m_req_min

    a = 1.0
    fa = f(a)          # >0（因为 M(1)=1 > m_req_min）
    b = _upper_bound_for_low_gain(k, q, m_req_min, start=1.0)
    fb = f(b)          # <0（按上界定义）
    fn = _f_bisect(f, a, b, fa, fb)
    return {"fn": fn, "feasible": True, "reason": ""}


def solve_gain_frequency(k: float, q_min_branch: float, m_req_max: float,
                         q_max_branch: float, m_req_min: float) -> dict:
    """合并求解 ``fn_min``（用 ``q_min_branch`` @ ``m_req_max``）与
    ``fn_max``（用 ``q_max_branch`` @ ``m_req_min``）。

    两条时间链可属于不同 Q（低输入+过载 用 Q_overload，高输入+满载 用 Q_full）。
    返回 dict 包含 ``fn_min``、``fn_max``、各自的 ``feasible`` 与原因，
    以及 ``M_available``(=M_boundary at q_min_branch)、``fn_boundary``。
    """
    r_min = solve_fn_min(k, q_min_branch, m_req_max)
    r_max = solve_fn_max(k, q_max_branch, m_req_min)
    fs_min_ret = r_min["fn"]
    fs_max_ret = r_max["fn"]
    op = {
        "fn_min": r_min["fn"], "fn_min_feasible": r_min["feasible"],
        "fn_min_reason": r_min["reason"],
        "fn_max": r_max["fn"], "fn_max_feasible": r_max["feasible"],
        "fn_max_reason": r_max["reason"],
        "fn_boundary": r_min["fn_boundary"],
        "M_boundary": r_min["M_boundary"],
    }
    # 只有当 fn_min 可行时才会给出物理上依然单调的工程频率范围
    op["fn_range_ok"] = r_min["feasible"] and r_max["feasible"] and \
        fs_min_ret <= fs_max_ret
    return op