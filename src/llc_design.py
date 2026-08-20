# -*- coding: utf-8 -*-
"""LLC 工程设计纯数学层（纯 Python，无 NumPy / Matplotlib 依赖）。

用于把"工程规格"换算成谐振腔参数、所需增益与满载/过载 Q，并给出推荐的
谐振 Q。全部为标量计算，因此只要一个纯 Python 实现即可同时服务
(1) EXE 运行路径 与 (2) 无 GUI 单元测试，无需 numpy 镜像层。

统一数学定义（与 :mod:`llc_py` / :mod:`llc_model` 完全一致）：

    K  = Lm / Lr                    励磁电感比
    fn = fs / fr                    归一化开关频率
    fr = 1 / (2π·sqrt(Lr·Cr))       串联谐振频率
    Zr = sqrt(Lr/Cr)                特征阻抗
    Q  = Zr / Re                    品质因数

关键的工程推导（本模块负责）：
    Re = 8·n²·RL / π²               整流器折算到原边的等效交流负载
    RL = Vo² / Pout                 负载电阻
    半桥：Mreq = 2·n·(Vo+Vdrop)/Vin
    全桥：Mreq = n·(Vo+Vdrop)/Vin
    自动匝比 n（令标称增益 = 1）：
        半桥 n = Vin_nom / (2·(Vo+Vdrop))
        全桥 n = Vin_nom / (Vo+Vdrop)

过载通过 "不同负载 → 不同 Re → 不同 Q" 体现，**严禁**把 M 直接乘过载倍率：
    Re_full     = 8·n²·Vo² / (π²·Pout)
    Re_overload = 8·n²·Vo² / (π²·Pout·OL)
    Q_full      = Zr / Re_full
    Q_overload  = Zr / Re_overload

谐振腔参数（给定 fr、Re、Q、K）：
    Zr = Q · Re                      （严禁写成 Zr = Re / Q）
    Lr = Zr / (2π·fr)
    Cr = 1 / (2π·fr·Zr)
    Lm = K · Lr
"""

from __future__ import annotations

import math

__all__ = [
    "BRIDGE_HALF",
    "BRIDGE_FULL",
    "RECT_CT_DIODE",
    "RECT_CT_SR",
    "RECT_FB_DIODE",
    "RECT_FB_SR",
    "BRIDGES",
    "RECTIFIERS",
    "RECT_PATH_DIODES",
    "gain_constant",
    "rectifier_output_offset",
    "turns_ratio_auto",
    "m_required",
    "load_resistance",
    "equivalent_resistance",
    "re_from_spec",
    "resonant_tank",
    "resonant_tank_from_q",
    "q_from_re",
    "back_calc_actual",
    "recommend_q",
    "validate_spec",
    "DesignSpec",
]

#: 原边拓扑
BRIDGE_HALF = "half"
BRIDGE_FULL = "full"
BRIDGES = (BRIDGE_HALF, BRIDGE_FULL)

#: 次级整流形式
RECT_CT_DIODE = "ct_diode"   # 中心抽头 + 二极管
RECT_CT_SR = "ct_sr"         # 中心抽头 + SR
RECT_FB_DIODE = "fb_diode"   # 全桥整流 + 二极管
RECT_FB_SR = "fb_sr"         # 全桥整流 + SR
RECTIFIERS = (RECT_CT_DIODE, RECT_CT_SR, RECT_FB_DIODE, RECT_FB_SR)

#: 每种次级整流在一条导通回路里串入的二极管/SR 压降个数。
#: 中心抽头整流输出回路串 1 个结压降；全桥整流串 2 个结压降。
RECT_PATH_DIODES = {
    RECT_CT_DIODE: 1,
    RECT_CT_SR: 1,
    RECT_FB_DIODE: 2,
    RECT_FB_SR: 2,
}


def gain_constant(bridge: str) -> float:
    """电压增益公式中的拓扑常数：半桥 → 2，全桥 → 1。

    依据 ``Mreq = c · n · (Vo + Vdrop) / Vin``，其中半桥原边电压利用率减半。
    """
    bridge = (bridge or "").lower()
    if bridge == BRIDGE_HALF:
        return 2.0
    if bridge == BRIDGE_FULL:
        return 1.0
    raise ValueError(f"未知拓扑：{bridge!r}，应为 {BRIDGE_HALF}/{BRIDGE_FULL}")


def rectifier_output_offset(rect: str, vf_sr: float) -> float:
    """次级整流在一条导通回路中的总压降 ``Vdrop``（并入输出串的电平）。

    使用用户输入的结压降 ``vf_sr`` 乘上该整流形式的串接压降个数。
    """
    rect = (rect or "").lower()
    if rect not in RECTIFIERS:
        raise ValueError(f"未知整流形式：{rect!r}，应为 {RECTIFIERS}")
    try:
        d = float(vf_sr)
    except (TypeError, ValueError) as exc:  # pragma: no cover
        raise ValueError(f"整流压降必须为数值：{vf_sr!r}") from exc
    if not math.isfinite(d) or d < 0.0:
        raise ValueError(f"整流压降必须 >= 0：{vf_sr!r}")
    return RECT_PATH_DIODES[rect] * d


def turns_ratio_auto(bridge: str, vin_nom: float, vo: float, vdrop: float) -> float:
    """自动理论匝比 n = Np/Ns。

    中心抽头时 Ns 为单个半绕组匝数。令标称输入下增益 = 1：
        半桥 n = Vin_nom / (2·(Vo + Vdrop))
        全桥 n = Vin_nom / (Vo + Vdrop)
    """
    c = gain_constant(bridge)
    vin_nom = float(vin_nom)
    vo = float(vo)
    vdrop = float(vdrop)
    denom = c * (vo + vdrop)
    if denom <= 0.0:
        raise ValueError(f"Vo + Vdrop 必须 > 0：vo={vo!r}, vdrop={vdrop!r}")
    if vin_nom <= 0.0:
        raise ValueError(f"Vin_nom 必须 > 0：{vin_nom!r}")
    return vin_nom / denom


def m_required(bridge: str, n: float, vo: float, vdrop: float, vin: float) -> float:
    """在给定输入电压下所需的 FHA 电压增益 ``Mreq``。

        半桥：Mreq = 2·n·(Vo + Vdrop) / Vin
        全桥：Mreq = n·(Vo + Vdrop) / Vin
    """
    c = gain_constant(bridge)
    n = float(n)
    vo = float(vo)
    vdrop = float(vdrop)
    vin = float(vin)
    if vin <= 0.0:
        raise ValueError(f"Vin 必须 > 0：{vin!r}")
    return c * n * (vo + vdrop) / vin


def load_resistance(vo: float, pout: float) -> float:
    """负载电阻 ``RL = Vo² / Pout``。"""
    vo = float(vo)
    pout = float(pout)
    if pout <= 0.0:
        raise ValueError(f"Pout 必须 > 0：{pout!r}")
    return vo * vo / pout


def equivalent_resistance(n: float, rl: float) -> float:
    r"""整流器折算到原边的 FHA 等效交流负载 ``Re = 8·n²·RL / π²``。"""
    n = float(n)
    rl = float(rl)
    if rl < 0.0:
        raise ValueError(f"RL 必须 >= 0：{rl!r}")
    return 8.0 * n * n * rl / (math.pi * math.pi)


def re_from_spec(n: float, vo: float, pout: float) -> float:
    r"""由规格直接算满载等效负载 ``Re = 8·n²·Vo² / (π²·Pout)``。"""
    return equivalent_resistance(n, load_resistance(vo, pout))


def resonant_tank(fr_hz: float, re: float, q: float, k: float) -> dict:
    r"""给定 ``fr``、``Re``、``Q``、``K`` 设计谐振腔。

    先定特征阻抗 ``Zr = Q·Re``（**严禁** Zr = Re/Q），再：
        Lr = Zr / (2π·fr)
        Cr = 1 / (2π·fr·Zr)
        Lm = K·Lr
    ``fr_hz`` 为物理频率（Hz）。返回含 ``Zr``/``Lr``/``Cr``/``Lm`` 的 dict。
    """
    fr_hz = float(fr_hz)
    re = float(re)
    q = float(q)
    k = float(k)
    if fr_hz <= 0.0:
        raise ValueError(f"fr 必须 > 0（Hz）：{fr_hz!r}")
    if re <= 0.0:
        raise ValueError(f"Re 必须 > 0：{re!r}")
    if q < 0.0:
        raise ValueError(f"Q 必须 >= 0：{q!r}")
    if k <= 0.0:
        raise ValueError(f"K 必须 > 0：{k!r}")
    zr = q * re
    w = 2.0 * math.pi * fr_hz
    lr = zr / w
    cr = 1.0 / (w * zr)
    lm = k * lr
    return {"Zr": zr, "Lr": lr, "Cr": cr, "Lm": lm}


def resonant_tank_from_q(fr_hz: float, re: float, q: float, k: float) -> dict:
    """别名：``resonant_tank``，按 fr/Re/Q/K 计算并返回谐振腔参数。"""
    return resonant_tank(fr_hz, re, q, k)


def q_from_re(zr: float, re: float) -> float:
    """品质因数 ``Q = Zr / Re``。"""
    zr = float(zr)
    re = float(re)
    if re <= 0.0:
        raise ValueError(f"Re 必须 > 0：{re!r}")
    return zr / re


def back_calc_actual(lr_actual, cr_actual, lm_actual) -> dict:
    r"""由实际谐振腔元件反算：``fr_actual``、``K_actual``、``Zr_actual``。

        fr_actual = 1 / (2π·sqrt(Lr·Cr))
        K_actual  = Lm / Lr
        Zr_actual = sqrt(Lr/Cr)
    用于"理论参数 / 实际采用参数"分离后的实际再验算。
    """
    lr = float(lr_actual)
    cr = float(cr_actual)
    lm = float(lm_actual)
    if lr <= 0.0 or cr <= 0.0:
        raise ValueError(f"Lr/Cr 必须 > 0：Lr={lr_actual!r}, Cr={cr_actual!r}")
    if lm <= 0.0:
        raise ValueError(f"Lm 必须 > 0：{lm_actual!r}")
    fr_actual = 1.0 / (2.0 * math.pi * math.sqrt(lr * cr))
    k_actual = lm / lr
    zr_actual = math.sqrt(lr / cr)
    return {"fr": fr_actual, "K": k_actual, "Zr": zr_actual}


# ---------------------------------------------------------------------------
# 推荐 Q（自动模式启发式）
# ---------------------------------------------------------------------------
# 在 "目标峰值增益 = M_req_max × 裕量系数" 的约束下反解 Q：
#     选中 Q 曲线的增益峰值 M_peak(K, Q) 随 Q 增大而减小 → 单调，可二分反解。
# 这只是"推荐"，绝不强制；用户在 UI 中仍可手动覆盖 Q。

def _q_curve_peak(k: float, q: float) -> float:
    """当前 K/Q 下、感性侧的增益峰值（在阻容边界与 fn=1 之间采样求峰）。"""
    from llc_py import find_peak, llc_gain

    fnp = 1.0 / math.sqrt(1.0 + k)
    lo = fnp * (1.0 + 1e-3)
    hi = 1.0 - 1e-3
    n = 800
    fn = [lo + (hi - lo) * (i / (n - 1)) for i in range(n)]
    m = [float(llc_gain(f, k, q)) for f in fn]
    _, mpeak = find_peak(fn, m)
    return float(mpeak)


def recommend_q(k: float, m_req_max: float, margin: float = 1.05,
                q_lo: float = 0.05, q_hi: float = 6.0) -> float:
    """推荐谐振 Q（启发式，非强制）。

    反解使 ``M_peak(K, Q) ≈ m_req_max × margin`` 的 Q。若在最低 Q 下增益
    仍不够（即峰值无法达到目标），返回 ``q_lo`` 并在调用方标记"增益不足"。
    """
    k = float(k)
    m_req_max = float(m_req_max)
    margin = float(margin)
    target = m_req_max * margin
    if target <= 0.0 or k <= 0.0:
        raise ValueError(
            f"K 与 (M_req_max·margin) 必须 > 0：K={k!r}, target={target!r}")
    # 峰值随 Q 单调递减；若即便最小 Q 峰值也不足，直接给最小 Q 并返回 (值, False)
    if _q_curve_peak(k, q_lo) < target:
        return q_lo
    if _q_curve_peak(k, q_hi) > target:
        return q_hi
    lo, hi = q_lo, q_hi
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if _q_curve_peak(k, mid) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


# ---------------------------------------------------------------------------
# 规格校验（事务式更新入口：全部校验通过才允许提交）
# ---------------------------------------------------------------------------

class DesignSpec:
    """工程设计输入的完整规格（不可变数据容器，便于事务式校验）。"""

    __slots__ = (
        "bridge", "rect", "vin_min", "vin_nom", "vin_max", "vo", "pout",
        "vdrop", "efficiency", "overload", "turn_mode", "n_manual",
        "fr_hz", "k", "q_selected",
    )

    def __init__(self, *, bridge, rect, vin_min, vin_nom, vin_max, vo,
                 pout, vdrop, efficiency, overload, turn_mode, n_manual,
                 fr_hz, k, q_selected):
        lenient = __import__("math").isfinite
        self.bridge = bridge
        self.rect = rect
        self.vin_min = float(vin_min)
        self.vin_nom = float(vin_nom)
        self.vin_max = float(vin_max)
        self.vo = float(vo)
        self.pout = float(pout)
        self.vdrop = float(vdrop)
        self.efficiency = float(efficiency)
        self.overload = float(overload)
        self.turn_mode = turn_mode
        self.n_manual = float(n_manual)
        self.fr_hz = float(fr_hz)
        self.k = float(k)
        self.q_selected = float(q_selected)


def validate_spec(s: DesignSpec) -> list[str]:
    """返回当前规格的全部错误信息列表；返回 ``[]`` 表示通过。

    规则（与工程约束一致，见需求二十六）：
        Vin_min > 0；Vin_min <= Vin_nom <= Vin_max；Vo > 0；Pout > 0；
        n > 0；fr > 0；K > 0；Q >= 0；0 < η <= 1；overload > 0。
    """
    errors: list[str] = []
    f = math.isfinite
    vin_min, vin_nom, vin_max = s.vin_min, s.vin_nom, s.vin_max
    if not (f(vin_min) and vin_min > 0):
        errors.append("Vin_min 必须 > 0")
    if not (f(vin_nom) and vin_nom > 0):
        errors.append("Vin_nom 必须 > 0")
    if not (f(vin_max) and vin_max > 0):
        errors.append("Vin_max 必须 > 0")
    if f(vin_min) and f(vin_nom) and vin_nom < vin_min:
        errors.append("Vin_nom 不能小于 Vin_min")
    if f(vin_nom) and f(vin_max) and vin_nom > vin_max:
        errors.append("Vin_nom 不能大于 Vin_max")
    if not (f(s.vo) and s.vo > 0):
        errors.append("Vo 必须 > 0")
    if not (f(s.pout) and s.pout > 0):
        errors.append("Pout 必须 > 0")
    if not (f(s.vdrop) and s.vdrop >= 0):
        errors.append("整流压降必须 >= 0")
    if not (f(s.efficiency) and 0.0 < s.efficiency <= 1.0):
        errors.append("效率 η 必须在 (0, 1]")
    if not (f(s.overload) and s.overload > 0):
        errors.append("过载倍率必须 > 0")
    if s.turn_mode != "manual":
        if not (f(s.n_manual) and s.n_manual > 0):
            errors.append("手动匝比 n 必须 > 0")
    if not (f(s.fr_hz) and s.fr_hz > 0):
        errors.append("fr 必须 > 0")
    if not (f(s.k) and s.k > 0):
        errors.append("K 必须 > 0")
    if not (f(s.q_selected) and s.q_selected >= 0):
        errors.append("Q 必须 >= 0")
    return errors


# ---------------------------------------------------------------------------
# 顶层设计计算（校验通过后调用；异常会向上抛出，由调用方事务式处理）
# ---------------------------------------------------------------------------

def compute_design(s: DesignSpec) -> dict:
    """把工程规格换算为一整套设计量（RoI：模块级标量计算，无绘图副作用）。

    返回 dict 涵盖：匝比 n、Vdrop、RL、Re_full、Re_overload、M_req(in/out 档)、
    Q_full、Q_overload、谐振腔理论参数、实际参数反算、可行性与裕量判据所需量。
    """
    errs = validate_spec(s)
    if errs:
        raise ValueError("；".join(errs))

    ret: dict = {}

    # 次级导通压降
    vdrop = rectifier_output_offset(s.rect, s.vdrop)
    ret["vdrop"] = vdrop

    # 匝比
    if s.turn_mode == "manual":
        n = s.n_manual
        n_auto = turns_ratio_auto(s.bridge, s.vin_nom, s.vo, vdrop)
        ret["n_mode"] = "manual"
        ret["n_auto"] = n_auto
    else:
        n = turns_ratio_auto(s.bridge, s.vin_nom, s.vo, vdrop)
        ret["n_mode"] = "auto"
        ret["n_auto"] = n
    ret["n"] = n

    # 负载 / 等效负载（满载与过载）
    rl_full = load_resistance(s.vo, s.pout)
    ret["RL_full"] = rl_full
    ret["Re_full"] = equivalent_resistance(n, rl_full)
    pout_ol = s.pout * s.overload
    ret["Pout_overload"] = pout_ol
    ret["RL_overload"] = load_resistance(s.vo, pout_ol)
    ret["Re_overload"] = equivalent_resistance(n, ret["RL_overload"])

    # 所需增益：低输入→高增益(M_req_max)，高输入→低增益(M_req_min)
    ret["M_req_min"] = m_required(s.bridge, n, s.vo, vdrop, s.vin_max)
    ret["M_req_nom"] = m_required(s.bridge, n, s.vo, vdrop, s.vin_nom)
    ret["M_req_max"] = m_required(s.bridge, n, s.vo, vdrop, s.vin_min)

    # 谐振腔（用选定 Q 与满载 Re 设计，使 Q = Zr/Re_full）
    tank = resonant_tank(s.fr_hz, ret["Re_full"], s.q_selected, s.k)
    ret.update(_TANK_KEYS(tank))
    zr = tank["Zr"]
    ret["Zr"] = zr
    # 不同负载 → 不同 Q
    ret["Q_full"] = q_from_re(zr, ret["Re_full"])
    ret["Q_overload"] = q_from_re(zr, ret["Re_overload"])
    ret["Q_selected"] = s.q_selected

    # 输入侧功率（效率仅用于输入功率换算与提示，不直接改输出侧 FHA）
    ret["Pout_eff"] = s.pout / s.efficiency if s.efficiency > 0 else float("inf")
    return ret


def _TANK_KEYS(tank: dict) -> dict:
    """把谐振腔 dict 映射为带 _calc 后缀的键（理论计算值）。"""
    return {
        "Zr_calc": tank["Zr"], "Lr_calc": tank["Lr"],
        "Cr_calc": tank["Cr"], "Lm_calc": tank["Lm"],
    }