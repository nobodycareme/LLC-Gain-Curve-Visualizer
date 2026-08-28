# -*- coding: utf-8 -*-
"""LLC 结果/分析/建议文本生成（纯 Python，可无 GUI 单元测试）。

约定：分析项以 ``✓`` / ``⚠`` / ``✕`` 标记，且必须**基于实际计算结果**生成，
禁止输出泛泛无依据的建议。
"""

from __future__ import annotations

import math

__all__ = [
    "format_working_point",
    "format_design_results",
    "format_stress_results",
    "build_analysis",
    "build_suggestions",
    "compile_report",
    "format_key_results",
    "format_short_analysis",
    "format_short_suggestions",
]


def _fmt(x, nd=4, unit=""):
    if x is None:
        return "—"
    x = float(x)
    if math.isnan(x) or x != x:
        return "—"
    if math.isinf(x):
        return "∞"
    return f"{x:.{nd}f}{unit}"


def _fmt_freq(hz, nd=3):
    hz = float(hz)
    a = abs(hz)
    if a >= 1e6:
        return f"{hz/1e6:.{nd}f} MHz"
    if a >= 1e3:
        return f"{hz/1e3:.{nd}f} kHz"
    return f"{hz:.1f} Hz"


def _fmt_complex(c, nd=3):
    return f"|{abs(complex(c)):.{nd}f}|"


def format_working_point(v: dict) -> str:
    """当前工作点区块（对应右侧【当前工作点】）。"""
    fnp = v["fnp"]
    fnr = v["fnr"]
    return "\n".join([
        "K    = " + _fmt(v.get("K")),
        "Q    = " + _fmt(v.get("Q")),
        "fn   = " + _fmt(v.get("fn")),
        "M    = " + _fmt(v.get("Mfn")),
        "fr   = " + _fmt(v.get("fr_khz"), 3) + " kHz",
        "fs   = " + _fmt(v.get("fn", 1.0) * v.get("fr_khz", 0.0), 3) + " kHz",
        "fnp  = " + _fmt(fnp),
        "fp   = " + _fmt(fnp * v.get("fr_khz", 0.0), 3) + " kHz",
        "M(fnp)= " + _fmt(v.get("Mfnp")),
        "fnr  = " + _fmt(fnr),
        "M(fnr)= " + _fmt(v.get("Mfnr")),
        "Mpeak= " + _fmt(v.get("Mpeak")),
        "fnpeak=" + _fmt(v.get("fn_peak")),
        "fn_boundary = " + _fmt(v.get("fn_boundary")),
        "∠Zin = " + _region(v.get("region")),
    ])


def _region(r) -> str:
    if r == "inductive":
        return "感性区（∠Zin>0）"
    if r == "capacitive":
        return "容性区（∠Zin<0）"
    if r == "boundary":
        return "阻容边界（∠Zin≈0）"
    return str(r)


def format_design_results(e: dict) -> str:
    """工程设计结果区块。"""
    tank = e.get("tank", {})
    tr = "手动" if e.get("n_mode") == "manual" else "自动"
    lines = [
        f"拓扑：{'半桥' if e.get('bridge') == 'half' else '全桥'}  "
        f"整流：{_rect_label(e.get('rect'))}",
        f"n   = {_fmt(e.get('n'))}   （{tr}，理论 {_fmt(e.get('n_auto'))}）",
        f"η   = {_fmt(e.get('efficiency'), 3)}",
        "",
        "RL  = " + _fmt(e.get("RL_full")) + " Ω",
        "Re  = " + _fmt(e.get("Re_full")) + " Ω",
        "Zr  = " + _fmt(e.get("Zr_calc")) + " Ω",
        "",
        "Lr_calc = " + _fmt(_h(e.get("Lr_calc")), 2, " µH"),
        "Lm_calc = " + _fmt(_h(e.get("Lm_calc")), 2, " µH"),
        "Cr_calc = " + _fmt(_n(e.get("Cr_calc")), 2, " nF"),
        "",
        f"M_req_min = {_fmt(e.get('M_req_min'))}   "
        f"(Vin_max={_fmt(e.get('vin_max'))} V)",
        f"M_req_max = {_fmt(e.get('M_req_max'))}   "
        f"(Vin_min={_fmt(e.get('vin_min'))} V)",
        f"Q_full     = {_fmt(e.get('Q_full'))}",
        f"Q_overload = {_fmt(e.get('Q_overload'))}",
        "",
        f"fn_min = {_fmt(e.get('fn_min'))}      "
        f"(fs_min={_fmt(e.get('fs_min', 0.0), 3)} kHz)",
        f"fn_max = {_fmt(e.get('fn_max'))}      "
        f"(fs_max={_fmt(e.get('fs_max', 0.0), 3)} kHz)",
        "M_available/Boundary = " + _fmt(e.get("M_available")),
    ]
    if tank:
        lines.append("")
        lines.append("实际件值反算："
                     "fr=%s  K=%s  Zr=%s" % (
                         _fmt_freq(tank.get("fr")), _fmt(tank.get("K")),
                         _fmt(tank.get("Zr"), 2)))
    return "\n".join(lines)


def _h(x):
    """Henries → µH"""
    if x is None:
        return None
    return float(x) * 1e6


def _n(x):
    """Farads → nF"""
    if x is None:
        return None
    return float(x) * 1e9


def _rect_label(r) -> str:
    return {
        "ct_diode": "中心抽头二极管整流", "ct_sr": "中心抽头同步整流",
        "fb_diode": "全桥二极管整流", "fb_sr": "全桥同步整流",
    }.get(r, str(r))


def format_stress_results(s: dict) -> str:
    """电流与应力区块（标注 FHA estimate）。"""
    lines = [
        "（FHA estimate）",
        "Ioe_rms = " + _fmt(s.get("ioe_rms")) + " A   （原边折算）",
        "Im_rms  = " + _fmt(s.get("im_rms")) + " A",
        "Ir_rms  = " + _fmt(s.get("ir_rms")) + " A",
        "Ir_peak = " + _fmt(s.get("ir_peak")) + " A",
        "",
    ]
    sec = s.get("secondary", {}) or {}
    if sec.get("total_secondary_rms") is not None:
        lines.append("次级总 RMS = " + _fmt(sec.get("total_secondary_rms")) + " A")
    if sec.get("ct_half_rms") is not None:
        lines.append("CT 单绕组 RMS = " + _fmt(sec.get("ct_half_rms")) + " A")
        lines.append("CT 单绕组 AVG = " + _fmt(sec.get("ct_half_avg")) + " A")
    if sec.get("fb_winding_rms") is not None:
        lines.append("FB 单绕组 RMS = " + _fmt(sec.get("fb_winding_rms")) + " A")
    cr = s.get("cr", {}) or {}
    if cr:
        lines += [
            "",
            "Cr Irms   = " + _fmt(cr.get("icr_rms")) + " A   （= Ir_rms）",
            "Cr Ipeak  = " + _fmt(cr.get("icr_peak")) + " A",
            "Cr Vac,rms= " + _fmt(cr.get("vcr_ac_rms")) + " V",
            "Cr Vrms   = " + _fmt(cr.get("vcr_rms")) + " V",
            "Cr Vpeak  = " + _fmt(cr.get("vcr_peak")) + " V",
        ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 分析 / 建议（基于实际计算结果，禁止空泛）
# ---------------------------------------------------------------------------

def _margin_req(e):
    ma = e.get("M_available")
    mr = e.get("M_req_max")
    if ma is None or mr is None or not mr or math.isnan(ma) or math.isnan(mr):
        return None
    return (float(ma) - float(mr)) / float(mr)


def build_analysis(e: dict, s: dict | None = None) -> list[tuple[str, str]]:
    """返回 ``[(flag, text), ...]``，flag ∈ {✓, ⚠, ✕}。"""
    out: list[tuple[str, str]] = []
    s = s or {}

    # 增益能力
    ms = _margin_req(e)
    if e.get("fn_min_feasible"):
        ms = _margin_req(e)
        if ms is not None and ms < 0.10:
            out.append(("⚠", "增益裕量偏低（M_available 仅高于 M_req_max %.1f%%）"
                        % (ms * 100)))
        else:
            out.append(("✓", "增益满足（M_req_max 可达）"))
    else:
        out.append(("✕", "增益能力不足：M_req_max 超过 M_boundary"))

    # 最低频率仍在感性区
    fnb = e.get("fn_boundary")
    fnmin = e.get("fn_min")
    if fnmin is not None and fnb is not None and not math.isnan(fnmin):
        if fnmin >= fnb - 1e-9:
            out.append(("✓", "最低频率仍在感性区（fn_min ≥ fn_boundary）"))
        else:
            out.append(("⚠", "最低频率位于阻容边界电容侧"))

    # 频率跨度
    fmax = e.get("fn_max")
    fmin = e.get("fn_min")
    if fmin and fmax and fmin > 0:
        span = fmax / fmin
        if span > 1.5:
            out.append(("⚠", "频率跨度过大（fn_max/fn_min=%.2f）" % span))
        else:
            out.append(("✓", "频率跨度合理（%.2f）" % span))

    # Cr 电压应力
    cr = (s.get("cr") or {})
    vpk = cr.get("vcr_peak")
    vinmax = e.get("vin_max")
    if vpk and vinmax:
        if float(vpk) > 2.0 * float(vinmax):
            out.append(("⚠", "Cr 电压应力偏高（Vpeak=%.0f V）" % float(vpk)))
        else:
            out.append(("✓", "Cr 峰值电压在参考范围之内"))

    # 过载 Q 相对满载增幅
    qf, qo = e.get("Q_full"), e.get("Q_overload")
    if qf and qo:
        out.append(("✓", "过载 Q（%.3f）高于满载 Q（%.3f）" % (qo, qf)))
    if not out:
        out.append(("✓", "参数完备，未见明显异常"))
    return out


def build_suggestions(e: dict) -> list[str]:
    """基于实际结果给出有依据的建议。"""
    out: list[str] = []
    ms = _margin_req(e)
    if not e.get("fn_min_feasible") or (ms is not None and ms < 0.0):
        out.append("增益能力不足：建议增大 K（Lm/Lr）或降低设计 Q 以提升峰值增益，"
                   "或调整匝比 n 降低 M_req_max。")
    elif ms is not None and ms < 0.10:
        out.append("增益裕量偏低：建议把 Q 略调低，给最大增益留出 >=10% 裕量。")
    qf, qo = e.get("Q_full"), e.get("Q_overload")
    if qf and qo and qo > qf * 1.2:
        out.append("过载工况使 Q 明显升高，建议核对过载倍率与热设计余量。")
    cr = e.get("cr") or {}
    vpk = cr.get("vcr_peak")
    vinmax = e.get("vin_max")
    if vpk and vinmax and float(vpk) > 2.0 * float(vinmax):
        out.append("Cr 峰值电压较高：建议提高 Cr 耐压或降低 Vin_max 区间的谐振电流。")
    fmax, fmin = e.get("fn_max"), e.get("fn_min")
    if fmin and fmax and fmin > 0 and fmax / fmin > 1.5:
        out.append("频率范围跨度过大：建议重估 K 取值以压缩频率范围，"
                   "或确认控制环路能在该范围稳定运行。")
    if not out:
        out.append("当前设计在给定的 K/Q/匝比/负载下满足增益与频率范围要求，"
                   "无需调整。")
    return out


def compile_report(v: dict, e: dict, stress: dict) -> str:
    """把三块合成单一文本（用于结果区整体展示，测试用）。"""
    parts = ["【当前工作点】", format_working_point(v), "",
             "【工程设计结果】", format_design_results(e), "",
             "【电流与应力】", format_stress_results(stress)]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 右侧精简分层（需求 5.1）：默认只显示关键结果 + 精简分析/建议。
# ---------------------------------------------------------------------------

def format_key_results(v: dict, e: dict | None = None,
                       s: dict | None = None) -> str:
    """右侧默认【关键结果】精简区块：关键信息前置。"""
    lines = ["【关键结果】"]
    lines.append("当前：")
    lines.append("  K    = " + _fmt(v.get("K")))
    lines.append("  Q    = " + _fmt(v.get("Q")))
    lines.append("  fn   = " + _fmt(v.get("fn")))
    lines.append("  M(fn)= " + _fmt(v.get("Mfn")))
    lines.append("  fs   = " + _fmt(v.get("fn", 1.0) * v.get("fr_khz", 0.0), 3)
                 + " kHz")
    if e:
        lines.append("谐振腔参数：")
        lines.append("  n    = " + _fmt(e.get("n")))
        lines.append("  Re   = " + _fmt(e.get("Re_full")) + " Ω")
        lines.append("  Lr   = " + _fmt(_h(e.get("Lr_calc")), 2, " µH"))
        lines.append("  Lm   = " + _fmt(_h(e.get("Lm_calc")), 2, " µH"))
        lines.append("  Cr   = " + _fmt(_n(e.get("Cr_calc")), 2, " nF"))
        lines.append("调频范围：")
        lines.append("  所需最小增益 M_req_min = " + _fmt(e.get("M_req_min")))
        lines.append("  所需最大增益 M_req_max = " + _fmt(e.get("M_req_max")))
        lines.append("  满载 Q     Q_full    = " + _fmt(e.get("Q_full")))
        lines.append("  过载 Q     Q_overload= " + _fmt(e.get("Q_overload")))
        lines.append("  最低归一化频率 fn_min  = " + _fmt(e.get("fn_min")))
        lines.append("  最高归一化频率 fn_max  = " + _fmt(e.get("fn_max")))
        lines.append("  最低开关频率 fs_min    = " + _fmt(e.get("fs_min", 0.0), 3) + " kHz")
        lines.append("  最高开关频率 fs_max    = " + _fmt(e.get("fs_max", 0.0), 3) + " kHz")
    if s:
        lines.append("最坏电流：")
        lines.append("  Ioe = " + _fmt(s.get("ioe_rms")) + " A")
        lines.append("  Im  = " + _fmt(s.get("im_rms")) + " A")
        lines.append("  Ir  = " + _fmt(s.get("ir_rms")) + " A")
        cr = s.get("cr") or {}
        if cr:
            lines.append("Cr 应力：")
            lines.append("  Irms = " + _fmt(cr.get("icr_rms")) + " A")
            lines.append("  Vpeak= " + _fmt(cr.get("vcr_peak")) + " V")
    return "\n".join(lines)


def build_result_cards(v: dict, e: dict | None = None,
                       s: dict | None = None,
                       engine_ok: bool = False,
                       engine_error: str | None = None) -> list:
    """结构化结果卡片（需求 10 重排）：``[(标题, [行, ...]), ...]``。

    每行是一个 tagged tuple：
    * ``("kv", 名称, 值)``       —— label|value 网格（名称次级、值加粗）
    * ``("flag", 标记, 消息)``   —— 设计分析（✓/⚠/✕ 着色）
    * ``("bullet", 文本)``       —— 建议条目

    固定顺序：当前工作点 → 谐振腔参数 → 调频范围 → 电流与应力
    → 设计分析 → 建议。数学定义不在此重复计算（Re 等由设计层给出）。
    与旧 ``build_result_sections`` 数据同源，是唯一数据来源。
    """
    sections = []
    sections.append(("当前工作点", [
        ("kv", "K", _fmt(v.get("K"))),
        ("kv", "Q", _fmt(v.get("Q"))),
        ("kv", "fn", _fmt(v.get("fn"))),
        ("kv", "M(fn)", _fmt(v.get("Mfn"))),
        ("kv", "fs", _fmt(v.get("fn", 1.0) * v.get("fr_khz", 0.0), 3) + " kHz"),
    ]))
    if e:
        # 谐振腔参数：含等效 AC 负载 Re = 8 n² Vo²/(π² Pout)（TI SLUP263 Eq.9）
        sections.append(("谐振腔参数", [
            ("kv", "拓扑 / 整流",
             f"{'半桥' if e.get('bridge') == 'half' else '全桥'} / "
             f"{_rect_label(e.get('rect'))}"),
            ("kv", "n", _fmt(e.get("n"))),
            ("kv", "等效交流负载 Re", _fmt(e.get("Re_full")) + " Ω"),
            ("kv", "谐振电感 Lr", _fmt(_h(e.get("Lr_calc")), 2, " µH")),
            ("kv", "励磁电感 Lm", _fmt(_h(e.get("Lm_calc")), 2, " µH")),
            ("kv", "谐振电容 Cr", _fmt(_n(e.get("Cr_calc")), 2, " nF")),
        ]))
        sections.append(("调频范围", [
            ("kv", "所需最小增益 M_req,min", _fmt(e.get("M_req_min"))),
            ("kv", "所需最大增益 M_req,max", _fmt(e.get("M_req_max"))),
            ("kv", "满载 Q  Q_full", _fmt(e.get("Q_full"))),
            ("kv", "过载 Q  Q_overload", _fmt(e.get("Q_overload"))),
            ("kv", "最低归一化频率 fn_min", _fmt(e.get("fn_min"))),
            ("kv", "最高归一化频率 fn_max", _fmt(e.get("fn_max"))),
            ("kv", "最低开关频率 fs_min", _fmt(e.get("fs_min", 0.0), 3) + " kHz"),
            ("kv", "最高开关频率 fs_max", _fmt(e.get("fs_max", 0.0), 3) + " kHz"),
        ]))
    if s:
        cr = s.get("cr") or {}
        rows = [
            ("kv", "Ioe（原边折算）", _fmt(s.get("ioe_rms")) + " A"),
            ("kv", "Im", _fmt(s.get("im_rms")) + " A"),
            ("kv", "Ir", _fmt(s.get("ir_rms")) + " A"),
        ]
        if cr:
            rows += [
                ("kv", "Cr Irms", _fmt(cr.get("icr_rms")) + " A"),
                ("kv", "Cr Vpeak", _fmt(cr.get("vcr_peak")) + " V"),
            ]
        sections.append(("电流与应力", rows))
    if engine_ok and e:
        items = build_analysis(e, s)
        items = sorted(items, key=lambda it: _FLAG_ORDER.get(it[0], 9))[:6]
        sections.append(("设计分析",
                         [("flag", flag, msg) for flag, msg in items]))
        sections.append(("建议",
                         [("bullet", x) for x in build_suggestions(e)[:5]]))
    elif engine_error:
        sections.append(("设计分析", [("flag", "⚠", "工程参数无效：" + engine_error)]))
    return sections


def build_result_sections(v: dict, e: dict | None = None,
                          s: dict | None = None,
                          engine_ok: bool = False,
                          engine_error: str | None = None) -> list:
    """向下兼容的字符串卡片：``[(标题, [行文本, ...]), ...]``。

    唯一数据来源是 :func:`build_result_cards`，这里仅把结构化行压平成与旧版
    **逐字符一致**的文本（保持 ``toPlainText()`` 及既有断言不变）。
    """
    out = []
    for title, rows in build_result_cards(v, e, s, engine_ok, engine_error):
        lines = []
        for row in rows:
            if row[0] == "kv":          # ("kv", name, value)
                lines.append(f"{row[1]:<16}  {row[2]}")
            elif row[0] == "flag":      # ("flag", flag, msg)
                lines.append(f"{row[1]}  {row[2]}")
            else:                       # ("bullet", text)
                lines.append(f"•  {row[1]}")
        out.append((title, lines))
    return out


#: 分析项优先级：✕ > ⚠ > ✓（严重问题优先展示）
_FLAG_ORDER = {"✕": 0, "⚠": 1, "✓": 2}


def format_short_analysis(e: dict | None, s: dict | None = None,
                          max_items: int = 6) -> str:
    """右侧默认【分析】精简区块：只保留最重要的前 max_items 条（需求 5.1）。

    按 ✕/⚠/✓ 优先级排序后截取，避免默认视图被大量辅助诊断占满。
    """
    if not e:
        return ""
    items = build_analysis(e, s)
    items = sorted(items, key=lambda it: _FLAG_ORDER.get(it[0], 9))
    items = items[:max_items]
    return "【分析】\n" + "\n".join(
        "  " + flag + " " + msg for flag, msg in items)


def format_short_suggestions(e: dict | None, max_items: int = 5) -> str:
    """右侧默认【建议】精简区块：只保留最重要的前 max_items 条（需求 5.1）。"""
    if not e:
        return ""
    items = build_suggestions(e)
    # 非"无需调整"的实质建议优先；仍保留默认兜底建议
    items = sorted(items, key=lambda x: 0 if x.startswith("当前设计") else 1)
    items = items[:max_items]
    return "【建议】\n" + "\n".join("  • " + x for x in items)