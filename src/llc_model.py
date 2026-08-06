# -*- coding: utf-8 -*-
"""
LLC 谐振变换器 FHA（基波近似）数学模型。

本项目统一采用以下唯一定义（与旧 MATLAB 原版的 ``K=fs/fr``/``L=Ln/Lr`` 相反，
已做彻底语义迁移，详见 BUILD_REPORT"符号体系纠正"一节）：

    K  = Lm / Lr           励磁电感比（本项目亦写作 k_ratio）
    fn = fs / fr           归一化开关频率
    Q  = sqrt(Lr/Cr) / Rac 品质因数
    M  = FHA 电压增益

唯一正确的 FHA 增益公式：

    M(fn, K, Q) = K·fn²
                  / sqrt( ((1+K)·fn² − 1)² + (Q·K·fn·(fn² − 1))² )

两个自然谐振点（归一化频率）：

    串联谐振：fnr = fr/fr = 1
    并联谐振：fnp = fp/fr = 1 / sqrt(1 + K)

实际频率换算：

    fs    = fn      · fr
    fp    = fnp     · fr
    fpeak = fn_peak · fr

本模块不依赖 GUI，可独立进行单元测试。
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "FN_MIN",
    "FN_MAX",
    "N_CURVE_POINTS",
    "Q_FAMILY",
    "DEFAULT_K",
    "DEFAULT_Q",
    "DEFAULT_FN",
    "DEFAULT_FR_KHZ",
    "DEFAULT_YMAX",
    "K_MIN",
    "K_MAX",
    "Q_MIN",
    "Q_MAX",
    "llc_gain",
    "llc_gain_from_parts",
    "fn_parallel",
    "fn_series",
    "make_fn_curve",
    "find_peak",
    "to_real_frequency",
]

# ---------------------------------------------------------------------------
# 与 MATLAB 源程序相同点数的常量
# ---------------------------------------------------------------------------

#: 归一化频率 fn 的扫描范围（等价于 MATLAB 的 ``logspace(-1, 1, 3000)``）
FN_MIN: float = 0.1
FN_MAX: float = 10.0
N_CURVE_POINTS: int = 3000

#: 固定参考 Q 曲线族（与 MATLAB ``Q_family`` 完全一致）
Q_FAMILY: tuple[float, ...] = (0.1, 0.2, 0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 10.0)

#: 励磁电感比 K（即 Lm/Lr）默认值；范围 1.5 ~ 10，线性滑块
DEFAULT_K: float = 5.0
DEFAULT_Q: float = 0.5
#: 归一化频率 fn 默认值；范围 0.1 ~ 10，对数滑块
DEFAULT_FN: float = 1.0
DEFAULT_FR_KHZ: float = 124.4
DEFAULT_YMAX: float = 2.2

#: 励磁电感比 K = Lm/Lr 的调节范围
K_MIN: float = 1.5
K_MAX: float = 10.0
Q_MIN: float = 0.05
Q_MAX: float = 10.0

#: 增益上限保护值。仅用于把数学上的 +inf（Q=0 且 fn=fnp 的极点）裁剪成
#: 一个有限的大数，避免绘图后端和峰值搜索出现异常。
#: 不改变公式本身，只影响奇点处的渲染。
GAIN_CLIP: float = 1.0e6


def llc_gain(fn, k_ratio: float, q: float):
    """计算 LLC FHA 增益 ``M(fn, K, Q)``。

    参数
    ----
    fn : float 或 array_like
        归一化开关频率 fs/fr。支持标量与 numpy 数组。
    k_ratio : float
        励磁电感比 Lm/Lr（K）。
    q : float
        品质因数 sqrt(Lr/Cr)/Rac。

    返回
    ----
    与 ``fn`` 同形状的 ``numpy`` 数组，或标量输入时返回 ``numpy.float64``。

    数值安全性
    ----------
    公式本身在 ``Q == 0`` 且 ``fn == fnp`` 时分母为零（真实的数学极点）。
    这里不修改公式，而是在计算后把 ``inf`` / ``NaN`` 裁剪为
    ``GAIN_CLIP`` / ``0.0``，从而保证下游绘图与峰值搜索不会崩溃。
    """
    fn_arr = np.asarray(fn, dtype=float)
    return llc_gain_from_parts(fn_arr, fn_arr ** 2, fn_arr ** 2 - 1.0, k_ratio, q)


def llc_gain_from_parts(fn, fn2, fn2m1, k_ratio: float, q: float):
    """复用预计算的 ``fn``、``fn²``、``fn²−1`` 计算增益（公式与 :func:`llc_gain` 完全一致）。

    用于拖动过程中的性能优化：``fn²`` 与 ``fn²−1`` 只与扫描向量有关，
    与 ``k_ratio``、``q`` 无关，可提前缓存，避免每次刷新重复计算数组幂。

    参数
    ----
    fn : array_like
        归一化频率扫描向量。
    fn2 : array_like
        与 ``fn`` 同形状的 ``fn ** 2``。
    fn2m1 : array_like
        与 ``fn`` 同形状的 ``fn ** 2 - 1``。
    k_ratio, q : float
        与 :func:`llc_gain` 含义相同。

    返回值语义与 :func:`llc_gain` 相同。
    """
    fn_arr = np.asarray(fn, dtype=float)
    fn2_arr = np.asarray(fn2, dtype=float)
    fn2m1_arr = np.asarray(fn2m1, dtype=float)
    k_ratio_f = float(k_ratio)
    q_f = float(q)

    # 与 MATLAB llcGain 完全一致的表达式（复用预计算中间量）
    numerator = k_ratio_f * fn2_arr
    denominator = np.sqrt(
        ((1.0 + k_ratio_f) * fn2_arr - 1.0) ** 2
        + (q_f * k_ratio_f * fn_arr * fn2m1_arr) ** 2
    )

    with np.errstate(divide="ignore", invalid="ignore"):
        M = numerator / denominator

    # 数值安全处理（不改变公式的数学特性，只处理奇点）
    M = np.where(np.isnan(M), 0.0, M)
    M = np.clip(M, 0.0, GAIN_CLIP)

    if np.isscalar(fn) or fn_arr.ndim == 0:
        return np.float64(M)
    return M


def fn_parallel(k_ratio: float) -> float:
    """并联谐振点归一化频率 ``fnp = 1 / sqrt(1 + K)``。"""
    return 1.0 / np.sqrt(1.0 + float(k_ratio))


def fn_series() -> float:
    """串联谐振点归一化频率 ``fnr = 1``。"""
    return 1.0


def make_fn_curve(n: int = N_CURVE_POINTS) -> np.ndarray:
    """生成对数分布的归一化频率扫描向量（等价于 ``logspace(-1, 1, n)``）。"""
    return np.logspace(np.log10(FN_MIN), np.log10(FN_MAX), int(n))


def find_peak(fn_curve: np.ndarray, m_curve: np.ndarray) -> tuple[float, float]:
    """在扫描范围内搜索当前 Q 曲线的增益峰值。

    与 MATLAB 实现一致：只在有限值上取最大，若无有限值则返回 ``(nan, nan)``。

    返回
    ----
    ``(fn_peak, m_peak)``
    """
    fn_curve = np.asarray(fn_curve, dtype=float)
    m_curve = np.asarray(m_curve, dtype=float)

    finite_mask = np.isfinite(m_curve)
    if not finite_mask.any():
        return float("nan"), float("nan")

    valid_index = np.flatnonzero(finite_mask)
    local_index = int(np.argmax(m_curve[finite_mask]))
    peak_index = int(valid_index[local_index])

    return float(fn_curve[peak_index]), float(m_curve[peak_index])


def to_real_frequency(fn, fr_khz: float):
    """把归一化频率换算成实际频率（kHz）：``f = fn * fr``。"""
    return np.asarray(fn, dtype=float) * float(fr_khz) if not np.isscalar(fn) \
        else float(fn) * float(fr_khz)