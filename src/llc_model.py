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
    # ---- 阻容分界线（Zin 相位判据）----
    "llc_input_impedance_normalized",
    "q_boundary_for_fn",
    "boundary_gain",
    "boundary_frequency",
    "input_region",
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


# ---------------------------------------------------------------------------
# 阻容分界线：输入阻抗相位判据（∠Zin = 0）
# ---------------------------------------------------------------------------
# 谐振特性阻抗 Zr = sqrt(Lr/Cr)，Q = Zr/Re。
# 将输入阻抗除以 Zr 得到无量纲形式：
#
#     z_in = j(fn - 1/fn) + j·K·fn / (1 + j·K·Q·fn)
#
# 实部/虚部解析展开：
#     令 a = K·fn，b = K·Q·fn
#     Re(z_in) = a·b / (1 + b²)            = K²·Q·fn² / (1 + (K·Q·fn)²)
#     Im(z_in) = (fn - 1/fn) + a/(1 + b²)  = fn - 1/fn + K·fn / (1 + (K·Q·fn)²)
#
# 阻容分界条件　Im(z_in) = 0：
#     fn - 1/fn + K·fn / (1 + (K·Q·fn)²) = 0
#
# 固定 K 时该方程对 Q 有解析解（有效区间 fm < fn < 1）：
#     Qb(fn) = sqrt( ((K+1)·fn² - 1) / (K²·fn²·(1 - fn²)) ),  fm = 1/sqrt(K+1)
#
# 把　Im=0 条件代入 FHA 增益公式可解析化简为边界增益：
#     Mb(fn) = sqrt( K·fn² / ((K+1)·fn² - 1) )
#
# 固定 K、Q 时的边界交点频率（数值稳定二次形式，A=(KQ)²，B=K+1-A）：
#     fnb² = 2 / (B + sqrt(B² + 4A))，Q→0 极限 fnb = 1/sqrt(K+1)


def llc_input_impedance_normalized(fn, k_ratio: float, q: float):
    """无量纲输入阻抗 ``z_in = j(fn − 1/fn) + j·K·fn / (1 + j·K·Q·fn)``。

    支持标量与数组输入。返回与 ``fn`` 同形状的复数数组/复数。
    阻容分界对应其虚部为 0（∠Zin = 0），见 :func:`input_region`。
    """
    fn_arr = np.asarray(fn, dtype=float)
    k_ratio_f = float(k_ratio)
    q_f = float(q)
    a = k_ratio_f * fn_arr            # K·fn
    b = k_ratio_f * q_f * fn_arr      # K·Q·fn
    den = 1.0 + b * b
    re = a * b / den
    im = (fn_arr - 1.0 / fn_arr) + a / den
    return re + 1j * im


def q_boundary_for_fn(fn, k_ratio: float):
    """固定 K 时，阻容边界处的 Q 值 ``Qb(fn)``。

    仅在　``1/sqrt(K+1) < fn < 1``　区间内有效并返回实数；
    区间外返回 ``nan``。
    """
    fn_arr = np.asarray(fn, dtype=float)
    u = fn_arr * fn_arr
    k = float(k_ratio)
    num = (k + 1.0) * u - 1.0
    den = k * k * u * (1.0 - u)
    with np.errstate(divide="ignore", invalid="ignore"):
        qb2 = num / den
    qb = np.sqrt(np.where((num > 0.0) & (den > 0.0), qb2, np.nan))
    if fn_arr.ndim == 0 or np.isscalar(fn):
        return float(qb)
    return qb


def boundary_gain(fn, k_ratio: float):
    """阻容边界增益 ``Mb(fn) = sqrt( K·fn² / ((K+1)·fn² − 1) )``。

    该式是把　``Im(z_in)=0``　代入 FHA 增益公式的解析结果，是
    **严格边界**，而非任何单条 Q 曲线的峰值。
    在　``fn → 1/sqrt(K+1)``　处趋于正无穷；区间下方返回 ``nan``。
    """
    fn_arr = np.asarray(fn, dtype=float)
    u = fn_arr * fn_arr
    k = float(k_ratio)
    den = (k + 1.0) * u - 1.0
    with np.errstate(divide="ignore", invalid="ignore"):
        m2 = k * u / den
    m = np.sqrt(np.where(den > 0.0, m2, np.nan))
    if fn_arr.ndim == 0 or np.isscalar(fn):
        return float(m)
    return m


def boundary_frequency(k_ratio: float, q: float) -> float:
    r"""固定 K、Q 时，该 Q 增益曲线与阻容边界的交点归一化频率 ``fnb``。

    由 ``Im(z_in)=0`` 得二次方程 ``A x² + B x − 1 = 0``，``x=fnb²``，
    ``A=(K·Q)²``，``B=K+1−A``。取正根并**按符号 B 分支**避免二次求根相消
    （quadratic root cancellation，两个接近大数相减会丢失有效位）：

    * ``Q=0``：解析极限 ``fnb = 1/sqrt(1+K)``；
    * ``B>=0``：``x = 2/(B + D)``（有理化形式，避免 −B+D 相消）；
    * ``B<0``：``x = (−B + D)/(2A)``（此时 −B 与 D 均为正、相加，无相消）；
    * 判别式 ``D = sqrt(B² + 4A)`` 以 ``hypot(B, 2·sqrt(A))`` 计算，
      避免 ``B²+4A`` 中间量无意义 overflow。

    返回值必然落在 ``[1/sqrt(1+K), 1]``。非法输入（K<=0、Q<0、NaN、±inf）
    抛出 :class:`ValueError`。注意：这两个公式数学上等价于同一正根，
    但不能合并成单一公式——``2/(B+D)`` 在 B<0 时自身会出现相消。
    """
    import math as _m

    if k_ratio is None or q is None:
        raise ValueError("K 与 Q 不能为 None")
    try:
        k = float(k_ratio)
        q = float(q)
    except (TypeError, ValueError) as exc:  # pragma: no cover - 类型测试分支
        raise ValueError(f"K/Q 必须可转为有限标量：K={k_ratio!r}, Q={q!r}") from exc
    if not (_m.isfinite(k) and _m.isfinite(q)):
        raise ValueError(f"K/Q 必须为有限数（禁止 NaN/±inf）：K={k_ratio!r}, Q={q!r}")
    if k <= 0.0:
        raise ValueError(f"K 必须 > 0：K={k_ratio!r}")
    if q < 0.0:
        raise ValueError(f"Q 必须 >= 0：Q={q!r}")

    fnp = 1.0 / np.sqrt(1.0 + k)
    if q == 0.0:
        return fnp
    a_kq = k * q                       # sqrt(A)（K、Q 非负）
    if not _m.isfinite(a_kq):
        # 已超出双精度可分辨范围，fb 理论值 → 1⁻，在表示极限处饱和到 1.0
        return 1.0
    a = a_kq * a_kq                    # A = (K·Q)²
    b = (k + 1.0) - a                  # B = K+1−A
    d = np.hypot(b, 2.0 * a_kq)        # sqrt(B² + 4A)，hypot 防 overflow
    if b >= 0.0:
        u = 2.0 / (b + d)              # B+D 无相消
    else:
        u = (-b + d) / (2.0 * a)       # −B 与 D 相加，无相消
    if not (0.0 < u <= 1.0):
        u = min(max(u, 0.0), 1.0)
    f = np.sqrt(u)
    return float(max(fnp, min(f, 1.0)))


def input_region(fn, k_ratio: float, q: float, tol: float = 1e-9) -> str:
    """根据输入阻抗虚部判定工作点所在区域。

    返回 ``"inductive"``（感性，∠Zin>0）、``"capacitive"``（容性，∠Zin<0）
    或 ``"boundary"``（阻容边界，|Im(z_in)| ≤ tol）。
    判据直接来自 :func:`llc_input_impedance_normalized` 的虚部，绝非肉眼估计。
    """
    z = llc_input_impedance_normalized(fn, k_ratio, q)
    im = np.imag(z) if np.ndim(z) else float(z.imag)
    if abs(float(im)) <= tol:
        return "boundary"
    return "inductive" if float(im) > 0.0 else "capacitive"