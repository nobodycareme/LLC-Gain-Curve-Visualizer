# -*- coding: utf-8 -*-
"""纯 Python 数值层（无 NumPy / Matplotlib 依赖）。

本模块是 LLC FHA 模型的一个**惰性慢速实现**，专门服务于应用打包路径：它让
绘制层与 GUI 不再 import NumPy / Matplotlib，从而显著缩小 EXE 并加快冷启动。

权威数学模型仍然是 :mod:`llc_model`（向量化、用于全部数学/绘图回归测试）。
本模块与其**逐位镜像**相同的公式与常数，并由 ``tests/test_llc_py_crosscheck.py``
用随机采样做交叉验证，确保两条实现数值一致、不会漂移。

符号体系（必须与 llc_model 完全一致）：
    K  = Lm / Lr
    fn = fs / fr
    Q  = sqrt(Lr/Cr) / Rac
    fr = 1 / (2*pi*sqrt(Lr*Cr))

本模块提供：
* 标量 / 序列（list / tuple / numpy 数组均可）兼容的增益与边界计算，
  序列输入返回 Python ``list``；
* 与 :mod:`llc_model` 相同的常量与回调兼容面（供 matplotlib 参考模块复用）。
"""

from __future__ import annotations

import math

__all__ = [
    "FN_MIN",
    "FN_MAX",
    "N_CURVE_POINTS",
    "Q_FAMILY",
    "GAIN_CLIP",
    "llc_gain",
    "llc_gain_from_parts",
    "fn_parallel",
    "fn_series",
    "make_fn_curve",
    "find_peak",
    # ---- 阻容分界线 ----
    "llc_input_impedance_normalized",
    "q_boundary_for_fn",
    "boundary_gain",
    "boundary_frequency",
    "input_region",
    # ---- 结果文本 ----
    "format_result_text",
]

# 与 llc_model 完全一致的常量
FN_MIN: float = 0.1
FN_MAX: float = 10.0
N_CURVE_POINTS: int = 3000
Q_FAMILY: tuple[float, ...] = (0.1, 0.2, 0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 10.0)
GAIN_CLIP: float = 1.0e6

# 与 llc_model 相同的界面默认值 / 调节范围常量（保持唯一符号体系）
DEFAULT_K: float = 5.0
DEFAULT_Q: float = 0.5
DEFAULT_FN: float = 1.0
DEFAULT_FR_KHZ: float = 124.4
DEFAULT_YMAX: float = 2.2
K_MIN: float = 1.5
K_MAX: float = 10.0
Q_MIN: float = 0.05
Q_MAX: float = 10.0


def _seq(x):
    """判断是否序列（list/tuple/numpy 数组等可迭代非标量）。"""
    try:
        return len(x)  # str 也返回，但这里不会传入 str
    except TypeError:
        return None


def _gain_scalar(fn2: float, fn2m1: float, fn: float, k: float, q: float) -> float:
    """单点增益（运算顺序与 llc_model 完全一致）。"""
    numerator = k * fn2
    denominator = math.sqrt(
        ((1.0 + k) * fn2 - 1.0) ** 2
        + (q * k * fn * fn2m1) ** 2
    )
    if denominator == 0.0:
        return GAIN_CLIP if numerator != 0.0 else 0.0
    m = numerator / denominator
    if math.isnan(m):
        return 0.0
    return min(max(m, 0.0), GAIN_CLIP)


def llc_gain(fn, k_ratio: float, q: float):
    """等价于 :func:`llc_model.llc_gain`，标量返回 float，序列返回 list。

    高频极限说明：对固定的 ``Q > 0``，当 ``fn → ∞`` 时 ``M → 0``；
    ``M → K/(1+K)`` 仅是 ``Q = 0``（空载）的特殊极限，不得将二者混淆。
    本函数对 ``k_ratio`` / ``q`` 一律先 ``float(...)`` 强转（标量与序列路径一致，
    即使入参为字符串也可安全解析）。
    """
    k = float(k_ratio)
    qq = float(q)
    n = _seq(fn)
    if n is None:
        return _gain_scalar(
            float(fn) ** 2, float(fn) ** 2 - 1.0, float(fn), k, qq
        )
    fn2 = [f * f for f in fn]
    return [
        _gain_scalar(f2, f2 - 1.0, f, k, qq)
        for f, f2 in zip(fn, fn2)
    ]


def llc_gain_from_parts(fn, fn2, fn2m1, k_ratio: float, q: float):
    """复用预计算的 ``fn``/``fn²``/``fn²−1``（等价 :func:`llc_model.llc_gain_from_parts`）。"""
    k = float(k_ratio)
    qq = float(q)
    n = _seq(fn)
    if n is None:
        return _gain_scalar(float(fn2), float(fn2m1), float(fn), k, q)
    return [
        _gain_scalar(float(f2), float(f2m1), float(f), k, qq)
        for f, f2, f2m1 in zip(fn, fn2, fn2m1)
    ]


def fn_parallel(k_ratio: float) -> float:
    return 1.0 / math.sqrt(1.0 + float(k_ratio))


def fn_series() -> float:
    return 1.0


def make_fn_curve(n: int = N_CURVE_POINTS) -> list:
    n = int(n)
    if n < 2:  # 至少 2 点，避免 (n-1) 作为分母为零
        raise ValueError(f"n 必须 >= 2，当前为 {n}")
    lo, hi = math.log10(FN_MIN), math.log10(FN_MAX)
    return [10.0 ** (lo + (hi - lo) * (i / (n - 1))) for i in range(n)]


def find_peak(fn_curve, m_curve) -> tuple[float, float]:
    """有限值上取最大值；无有限值返回 ``(nan, nan)``。

    使用 ``math.isfinite`` 同时排除 NaN 与 ±Inf（Inf 会通过 ``m == m`` 检查，
    故不能只用它判断）。
    """
    best = None
    peak_fn = peak_m = float("nan")
    for f, m in zip(fn_curve, m_curve):
        try:
            fv = float(f)
            mv = float(m)
        except (TypeError, ValueError):
            continue
        if math.isfinite(mv):
            if best is None or mv > best:
                best = mv
                peak_fn, peak_m = fv, mv
    if best is None:
        return float("nan"), float("nan")
    return peak_fn, peak_m


# ---------------------------------------------------------------------------
# 阻容分界线（∠Zin = 0）—— 纯 Python
# ---------------------------------------------------------------------------

def llc_input_impedance_normalized(fn, k_ratio: float, q: float):
    """无量纲输入阻抗，与 :func:`llc_model.llc_input_impedance_normalized` 等价。"""
    k = float(k_ratio)
    qq = float(q)
    n = _seq(fn)

    def one(f):
        a = k * f          # K·fn
        b = k * qq * f     # K·Q·fn
        den = 1.0 + b * b
        re = a * b / den
        im = (f - 1.0 / f) + a / den
        return complex(re, im)

    if n is None:
        return one(float(fn))
    return [one(float(f)) for f in fn]


def q_boundary_for_fn(fn, k_ratio: float):
    k = float(k_ratio)
    n = _seq(fn)

    def one(f):
        u = f * f
        num = (k + 1.0) * u - 1.0
        den = k * k * u * (1.0 - u)
        if num > 0.0 and den > 0.0:
            return math.sqrt(num / den)
        return float("nan")

    if n is None:
        return one(float(fn))
    return [one(float(f)) for f in fn]


def boundary_gain(fn, k_ratio: float):
    k = float(k_ratio)
    n = _seq(fn)

    def one(f):
        u = f * f
        den = (k + 1.0) * u - 1.0
        if den > 0.0:
            return math.sqrt(k * u / den)
        return float("nan")

    if n is None:
        return one(float(fn))
    return [one(float(f)) for f in fn]


def _validate_kq(k_ratio: float, q: float) -> None:
    """校验 K/Q 合法性，非法输入明确报错，绝不静默 abs/裁剪隐藏错误。"""
    if k_ratio is None or q is None:
        raise ValueError("K 与 Q 不能为 None")
    try:
        k = float(k_ratio)
        qq = float(q)
    except (TypeError, ValueError) as exc:  # pragma: no cover - 类型测试分支
        raise ValueError(f"K/Q 必须可转为有限标量：K={k_ratio!r}, Q={q!r}") from exc
    if not (math.isfinite(k) and math.isfinite(qq)):
        raise ValueError(f"K/Q 必须为有限数（禁止 NaN/±inf）：K={k_ratio!r}, Q={q!r}")
    if k <= 0.0:
        raise ValueError(f"K 必须 > 0：K={k_ratio!r}")
    if qq < 0.0:
        raise ValueError(f"Q 必须 >= 0：Q={q!r}")


def boundary_frequency(k_ratio: float, q: float) -> float:
    r"""固定 K、Q 时，该 Q 增益曲线与阻容边界（\_\_Zin=0）的交点归一化频率 ``fnb``。

    二次方程 ``A x² + B x − 1 = 0``，``x=fnb²``，``A=(K·Q)²``，``B=K+1−A``。
    取正根并**按符号 B 分支**避免二次求根相消（quadratic root cancellation）：

    * ``Q=0``：解析极限 ``fnb = 1/sqrt(1+K)``；
    * ``B>=0``：``x = 2/(B + D)``（有理化，避免 −B+D 相消）；
    * ``B<0``：``x = (−B + D)/(2A)``（此时 −B 与 D 均为正、相加，消除相消）；
    * 判别式 ``D = sqrt(B² + 4A)`` 以 ``math.hypot(B, 2·sqrt(A))`` 计算，
      避免 ``B²+4A`` 中间量无意义 overflow。

    返回值必然落在 ``[1/sqrt(1+K), 1]``。非法输入（K<=0、Q<0、NaN、±inf）
    抛出 :class:`ValueError`。
    """
    _validate_kq(k_ratio, q)
    k = float(k_ratio)
    q = float(q)
    fnp = 1.0 / math.sqrt(1.0 + k)
    if q == 0.0:
        return fnp
    a_kq = k * q                      # sqrt(A)（K、Q 非负）
    if not math.isfinite(a_kq):
        # 已超出双精度可分辨范围，fb 理论值 → 1⁻，在表示极限处饱和到 1.0
        return 1.0
    a = a_kq * a_kq                   # A = (K·Q)²
    b = (k + 1.0) - a                 # B = K+1−A
    d = math.hypot(b, 2.0 * a_kq)     # sqrt(B² + 4A)，hypot 防 overflow
    if b >= 0.0:
        u = 2.0 / (b + d)             # B+D 无相消
    else:
        u = (-b + d) / (2.0 * a)      # −B 与 D 相加，无相消
    if not (0.0 < u <= 1.0):
        u = min(max(u, 0.0), 1.0)
    f = math.sqrt(u)
    return float(max(fnp, min(f, 1.0)))


def input_region(fn, k_ratio: float, q: float, tol: float = 1e-9) -> str:
    z = llc_input_impedance_normalized(fn, k_ratio, q)
    im = z.imag if isinstance(z, complex) else z[0].imag
    if abs(im) <= tol:
        return "boundary"
    return "inductive" if im > 0.0 else "capacitive"


# ---------------------------------------------------------------------------
# 结果文本（原位于 llc_plot，移到此纯模块供 GUI 无 matplotlib 复用）
# ---------------------------------------------------------------------------

def format_result_text(v: dict) -> str:
    fr_khz = v["fr_khz"]
    fn_peak = v["fn_peak"]
    fp_khz = v["fnp"] * fr_khz
    fs_khz = v["fn"] * fr_khz
    fpeak_khz = fn_peak * fr_khz if _isfinite(fn_peak) else float("nan")

    lines = [
        "【当前可调参数】",
        f"  K    = {v['K']:.5f}",
        f"  Q    = {v['Q']:.5f}",
        f"  fn   = {v['fn']:.5f}",
        f"  M(fn)= {v['Mfn']:.5f}",
        f"  fs   = {fs_khz:.3f} kHz",
        "",
        "【工作区域】",
        f"  当前 fn 所在：{_region_label(v)}",
        f"  边界判定 fn_boundary = {v['fn_boundary']:.5f} (∠Zin=0)",
        f"  M(fn_boundary)      = {v['M_boundary']:.5f}",
        "",
        "【两个自然谐振频率点】",
        f"  并联谐振：fnp  = {v['fnp']:.5f}",
        f"            fp   = {fp_khz:.3f} kHz",
        f"            M(fnp)= {v['Mfnp']:.5f}",
        "",
        f"  串联谐振：fnr  = {v['fnr']:.5f}",
        f"            fr   = {fr_khz:.3f} kHz",
        f"            M(fnr)= {v['Mfnr']:.5f}",
        "",
        "【当前 Q 曲线峰值】",
        f"  fn_peak = {fn_peak:.5f}",
        f"  f_peak  = {fpeak_khz:.3f} kHz",
        f"  M_peak  = {v['Mpeak']:.5f}",
        "",
        "【曲线说明】",
        "  彩色细线：固定参考 Q 曲线族",
        "            Q=0.1/0.2/0.5/0.8/1/2/5/8/10",
        "  黑色粗线：滑块控制的当前 Q 曲线",
        "  深色虚线：阻容分界线（∠Zin = 0）",
        "",
        "  红色虚线 fnp    ：并联谐振频率",
        "  蓝色虚线 fnr=1  ：串联谐振频率",
        "  灰色点线 当前fn ：当前开关工作点",
        "",
        "  ○ 圆形：当前 Q 曲线的并联谐振点 fnp",
        "  □ 方形：当前 Q 曲线的串联谐振点 fnr=1",
        "  △ 三角：当前 Q 曲线的增益峰值",
        "  ◇ 菱形：当前归一化频率工作点 fn",
        "",
        "【工作区域说明】",
        "  容性区：∠Zin < 0（工作点位于阻容边界左侧）",
        "  感性区：∠Zin > 0（工作点位于阻容边界右侧）",
        "  阻容边界：∠Zin = 0，Im(Zin)≈0",
        "",
        "【参数影响】",
        "  K  改变：所有增益曲线一起变化",
        "  Q  改变：黑色粗线发生变化",
        "  fn 改变：工作点沿当前黑色曲线移动",
        "  fr 改变：只影响实际频率换算，",
        "           不改变归一化曲线形状",
        "",
        "【参数定义】",
        "  K  = Lm / Lr",
        "  fn = fs / fr",
        "  Q  = sqrt(Lr/Cr) / Rac",
    ]
    return "\n".join(lines)


def _region_label(v: dict) -> str:
    return {
        "inductive": "感性区（∠Zin > 0）",
        "capacitive": "容性区（∠Zin < 0）",
        "boundary": "阻容边界（∠Zin ≈ 0）",
    }.get(v.get("region"), v.get("region", "未知"))


def _isfinite(x) -> bool:
    try:
        import math as _m
        return _m.isfinite(float(x))
    except (TypeError, ValueError):
        return False