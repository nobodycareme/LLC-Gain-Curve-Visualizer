# -*- coding: utf-8 -*-
"""LLC FHA 相量工作点 / 次级电流 / 谐振电容应力（纯 Python，无第三方依赖）。

要点（谨记：所有结果均为 FHA 基波近似，UI 必须标注 "FHA estimate"）：

1. 任意工作点的相量求解（不只 fn=1）：
       ω = 2π·fs
       Zs = jω·Lr + 1/(jω·Cr)
       Zm = jω·Lm
       Zp = Zm ‖ Re
       Zin = Zs + Zp
       半桥 Vge_rms =  (√2/π)·Vin
       全桥 Vge_rms = (2√2/π)·Vin
       Ir  = Vge / Zin
       Voe = Ir · Zp
       Ioe = Voe / Re
       Im  = Voe / (jω·Lm)
       校核：Ir ≈ Ioe + Im（KCL）

2. 次级电流（按拓扑区分，中心抽头与全桥整流公式**不得混用**）：
       中心抽头：Ioe_secondary = n·Ioe_primary；
           理想 FHA：单半绕组 RMS = (π/4)·Io，单半绕组 AVG = Io/2
       全桥整流：单绕组（全波）RMS = π/(2√2)·Io

3. Cr 应力（Cr 与谐振支路串联，ICr = Ir）：
       ICr_rms = Ir_rms
       ICr_peak ≈ √2·Ir_rms
       VCr_ac_rms = Ir_rms / (ω·Cr)
       半桥 DC 偏置 VCr_dc ≈ Vin/2；全桥无 DC 偏置
       VCr_rms  = √(VCr_dc² + VCr_ac_rms²)
       VCr_peak = VCr_dc + √2·VCr_ac_rms
   严禁只用 Vin/2 当作 Cr 峰值电压。
"""

from __future__ import annotations

import math
import cmath

__all__ = [
    "half_bridge_fundamental_rms",
    "full_bridge_fundamental_rms",
    "fha_phasor",
    "secondary_currents",
    "cr_stress",
    "phasor_magnitude",
]

#: 半桥原边基波分量（Vge RMS）= √2/π × Vin
HALF_BRIDGE_K = math.sqrt(2.0) / math.pi
#: 全桥原边基波分量（Vge RMS）= 2√2/π × Vin
FULL_BRIDGE_K = 2.0 * math.sqrt(2.0) / math.pi


def half_bridge_fundamental_rms(vin: float) -> float:
    """半桥原边基波电压 RMS = √2/π × Vin。"""
    return HALF_BRIDGE_K * float(vin)


def full_bridge_fundamental_rms(vin: float) -> float:
    """全桥原边基波电压 RMS = 2√2/π × Vin。"""
    return FULL_BRIDGE_K * float(vin)


def phasor_magnitude(v) -> float:
    """复数幅值（纵使为 float 也转复数取模）。"""
    z = complex(v)
    return abs(z)


def fha_phasor(vin: float, fs_hz: float, lr: float, lm: float, cr: float,
               re: float, bridge: str) -> dict:
    """在任意 ``(Vin, fs, Lr, Lm, Cr, Re, topology)`` 下求 FHA 相量工作点。

    返回 dict：
        ``omega``    角频率(rad/s)
        ``Zin``      输入阻抗复数
        ``vge_rms``  原边基波电压 RMS
        ``ir``/``ir_rms``/``ir_peak``  原边谐振电流（复数 / RMS / 峰值）
        ``ioe_rms``  折算原边负载电流 RMS
        ``im_rms``   励磁电流 RMS
        ``voe_rms``  并联支路两端电压 RMS
        ``kcl_ir``、``kcl_sum``、``kcl_ok``：Ir ≈ Ioe + Im 的校核
    """
    vin = float(vin)
    fs_hz = float(fs_hz)
    lr = float(lr)
    lm = float(lm)
    cr = float(cr)
    re = float(re)
    if fs_hz <= 0.0 or lr <= 0.0 or lm <= 0.0 or cr <= 0.0 or re <= 0.0 or vin <= 0.0:
        raise ValueError("Vin/fs/Lr/Lm/Cr/Re 均必须 > 0")

    w = 2.0 * math.pi * fs_hz
    jw = 1j * w
    zs = jw * lr + 1.0 / (jw * cr)
    zm = jw * lm
    zp = (zm * re) / (zm + re)          # Zm ‖ Re
    zin = zs + zp

    if bridge == "full":
        vge = full_bridge_fundamental_rms(vin)
    elif bridge == "half":
        vge = half_bridge_fundamental_rms(vin)
    else:
        raise ValueError(f"未知拓扑：{bridge!r}，应为 half/full")

    ir = vge / zin                      # 原边谐振电流（复数，RMS 值）
    voe = ir * zp
    ioe = voe / re                      # 折算原边负载电流
    im = voe / zm                       # 励磁电流

    ir_rms = abs(ir)
    ioe_rms = abs(ioe)
    im_rms = abs(im)
    kcl_sum = ioe + im
    kcl_ok = abs(kcl_sum - ir) <= 1e-6 * max(ir_rms, 1e-12)

    return {
        "omega": w,
        "Zin": zin,
        "vge_rms": vge,
        "ir": ir, "ir_rms": ir_rms, "ir_peak": ir_rms * math.sqrt(2.0),
        "ioe_rms": ioe_rms,
        "voe_rms": abs(voe),
        "im_rms": im_rms,
        "kcl_ir": ir, "kcl_ioe_plus_im": kcl_sum, "kcl_ok": kcl_ok,
    }


def secondary_currents(rect: str, ioe_rms_primary: float, n: float,
                       io_dc: float) -> dict:
    """根据整流拓扑计算次级电流（理想 FHA 近似）。

    返回 dict：
        ``total_secondary_rms``：折算到次级的负载电流 RMS（总）= n·Ioe_primary
        ``ct_half_rms``：中心抽头单半绕组 RMS = (π/4)·Io（仅 CT 有效）
        ``ct_half_avg``：中心抽头单半绕组 AVG = Io/2（仅 CT 有效）
        ``fb_winding_rms``：全桥整流单绕组(全波) RMS = π/(2√2)·Io（仅 FB 有效）
    """
    n = float(n)
    ioe_rms_primary = float(ioe_rms_primary)
    io_dc = float(io_dc)
    total = n * ioe_rms_primary
    ret = {"total_secondary_rms": total}
    if rect == "ct_diode" or rect == "ct_sr":
        ret["ct_half_rms"] = (math.pi / 4.0) * io_dc
        ret["ct_half_avg"] = io_dc / 2.0
        ret["fb_winding_rms"] = None
    elif rect == "fb_diode" or rect == "fb_sr":
        ret["fb_winding_rms"] = (math.pi / (2.0 * math.sqrt(2.0))) * io_dc
        ret["ct_half_rms"] = None
        ret["ct_half_avg"] = None
    else:
        raise ValueError(f"未知整流形式：{rect!r}")
    return ret


def cr_stress(ir_rms: float, omega: float, cr: float, vin: float,
              bridge: str) -> dict:
    """谐振电容 Cr 的电流与电压应力。

        半桥 DC 偏置为 Vin/2，全桥为 0；AC 电压来自 Ir/(ωCr)。
    返回：``icr_rms``、``icr_peak``、``vcr_ac_rms``、``vcr_dc``、
    ``vcr_rms``、``vcr_peak``。
    """
    ir_rms = float(ir_rms)
    omega = float(omega)
    cr = float(cr)
    vin = float(vin)
    if omega <= 0.0 or cr <= 0.0:
        raise ValueError("omega/Cr 必须 > 0")
    icr_rms = ir_rms
    icr_peak = math.sqrt(2.0) * ir_rms
    vcr_ac_rms = ir_rms / (omega * cr)
    vcr_dc = (vin / 2.0) if (bridge == "half") else 0.0
    vcr_rms = math.sqrt(vcr_dc * vcr_dc + vcr_ac_rms * vcr_ac_rms)
    vcr_peak = vcr_dc + math.sqrt(2.0) * vcr_ac_rms
    return {
        "icr_rms": icr_rms, "icr_peak": icr_peak,
        "vcr_ac_rms": vcr_ac_rms, "vcr_dc": vcr_dc,
        "vcr_rms": vcr_rms, "vcr_peak": vcr_peak,
    }