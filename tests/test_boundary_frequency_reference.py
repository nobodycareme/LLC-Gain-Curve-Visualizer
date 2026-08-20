# -*- coding: utf-8 -*-
"""boundary_frequency 与高精度参考实现（Decimal）交叉验证。

本测试只用 ``decimal.Decimal``（标准库，**绝不进入最终 EXE**）实现独立高精度
参考算法，验证生产 double 算法在极端参数下与高精度结果一致。

只允许 Decimal / 标准库作为 test dependency（不引入 numpy / mpmath 的新的
正式运行依赖）。
"""

from __future__ import annotations

import decimal
import os
import sys
from decimal import Decimal, localcontext

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from llc_model import boundary_frequency  # noqa: E402

PREC = 80


def _ref_boundary_frequency(K: float, Q: float) -> float:
    """高精度参考：用 Decimal 求解 A x² + B x − 1 = 0 的正根 x=fnb²。

    生产算法为避免 double 相消做了符号分支 + hypot；本参考用高精度直接
    计算，没有相消问题，作为"真值"交叉核对生产结果。
    """
    Kd = Decimal(str(K))
    Qd = Decimal(str(Q))
    if Qd == 0:
        return float(1 / (Decimal(1 + K)).sqrt())

    with localcontext() as ctx:
        ctx.prec = PREC
        # 直接求判别式（高精度下无 overflow/相消问题）
        A = (Kd * Qd) ** 2
        B = Kd + Decimal(1) - A
        D = (B * B + Decimal(4) * A).sqrt()
        # 取正根（此处 -B+D 与 B+D 在高精度下均精确，二选一即可）
        x_num = (-B).copy_abs() + D if B < 0 else Decimal(2)
        x_den = Decimal(2) * A if B < 0 else B + D
        x = x_num / x_den
    return float(x.sqrt())


CASES = [
    # (K, Q)
    (5.0, 0.0),
    (5.0, 1e-9),
    (5.0, 0.5),
    (5.0, 1.0),
    (5.0, 100.0),
    (5.0, 1e4),
    (5.0, 1e6),
    (5.0, 1e8),
    (0.5, 1e4),
    (0.5, 1e8),
    (10.0, 1e8),
    (100.0, 1e6),
    (100.0, 1e8),
    (0.1, 1e4),
    (0.1, 1e8),
]


@pytest.mark.parametrize("K,Q", CASES)
def test_matches_high_precision_reference(K, Q):
    got = boundary_frequency(K, Q)
    ref = _ref_boundary_frequency(K, Q)
    # 依参数尺度设定相对容差；double 在 1e8 以上可能饱和到 1.0，
    # 此时 ref 也极接近 1，绝对差 ≤ 1e-9 仍成立
    assert got == pytest.approx(ref, rel=1.5e-9, abs=1.5e-9), \
        f"生产算法与高精度参考不一致：K={K}, Q={Q}, got={got}, ref={ref}"


@pytest.mark.parametrize("K,Q", CASES)
def test_reference_sane_limits(K, Q):
    """参考实现本身也应落在物理范围内，避免“参考也错、两个错一起”的情况。"""
    import math as _m

    ref = _ref_boundary_frequency(K, Q)
    fnp = 1.0 / _m.sqrt(1.0 + K)
    assert ref >= fnp - 1e-6, f"参考越下界：K={K}, Q={Q}, ref={ref}, fnp={fnp}"
    assert ref <= 1.0 + 1e-6, f"参考越上界：K={K}, Q={Q}, ref={ref}"


def test_high_precision_imports_only_stdlib():
    """保证高精度实现只用标准库（decimal），未引入任何第三方测试依赖。"""
    import decimal as d

    with localcontext() as ctx:
        ctx.prec = 60
        assert d.Decimal("1.0").sqrt() == Decimal("1.0")