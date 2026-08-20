# -*- coding: utf-8 -*-
"""增益曲线绘图层（不依赖 PySide6，便于无 GUI 环境下单元测试）。

本模块封装 :class:`GainPlot`，负责：

* 在给定的 Matplotlib ``Figure`` 上**一次性创建**全部图形对象；
* 后续刷新只调用 ``set_ydata`` / ``set_xdata`` / ``set_data`` 更新数据，
  绝不新建曲线、竖线、标记或文字对象
   （对应 MATLAB 原版"每动一次旧符号 Ln=Lm/Lr 就多一条虚线"的缺陷）；
* 提供**参数依赖增量更新**：

  * ``K``（= Lm/Lr）改变 → 重新计算全部固定参考 Q 曲线 + 当前 Q 曲线 + 峰值等；
  * ``Q`` 改变 → 只重新计算当前 Q 黑色曲线（固定参考曲线族不重算）；
  * ``fn``（= fs/fr）改变 → 只移动工作点竖线与标记，不重算任何整条曲线、不搜峰值、
    不重建图例；
  * ``fr`` 改变 → 不重算任何归一化曲线，只影响实际频率换算文本；
  * 纵轴上限改变 → 只 ``set_ylim``。

图例只在初始化时创建一次；当前 Q 数值需要变化时，只通过
``legend.get_texts()[idx].set_text(...)`` 原地更新文本，**绝不**每帧重建。

把绘图逻辑从 Qt 窗口中分离出来的好处是：即使运行环境没有安装 PySide6，
也可以用纯 Matplotlib（Agg 后端）对最关键的"对象不增长"回归进行验证。
"""

from __future__ import annotations

import numpy as np

from llc_model import (
    DEFAULT_FN,
    DEFAULT_K,
    DEFAULT_YMAX,
    FN_MAX,
    FN_MIN,
    Q_FAMILY,
    boundary_frequency,
    boundary_gain,
    find_peak,
    fn_parallel,
    fn_series,
    input_region,
    llc_gain,
    llc_gain_from_parts,
    make_fn_curve,
)

__all__ = ["GainPlot", "format_result_text"]


class GainPlot:
    """管理增益曲线图上的全部 Matplotlib 图形对象。

    所有长期存在的图形对象在初始化时创建一次，之后只更新数据/位置。
    ``stats`` 属性记录各类计算与重建的次数，供回归测试断言
    （例如"fn 改变时不重算固定曲线"）。
    """

    def __init__(self, figure) -> None:
        import matplotlib

        self.figure = figure
        self.ax = figure.add_subplot(111)
        self.fn_curve = make_fn_curve()

        # ---- 预计算与 k_ratio/Q 无关的中间量，拖动时复用 ----
        self.fn2 = self.fn_curve ** 2
        self.fn2m1 = self.fn2 - 1.0

        ax = self.ax
        ax.set_xscale("log")
        ax.set_xlim(FN_MIN, FN_MAX)
        ax.set_ylim(0.0, DEFAULT_YMAX)
        ax.grid(True, which="major", linestyle="-", linewidth=0.7, alpha=0.55)
        ax.grid(True, which="minor", linestyle=":", linewidth=0.45, alpha=0.35)
        ax.set_axisbelow(True)
        ax.set_xlabel("归一化频率 fn = fs / fr", fontsize=11)
        ax.set_ylabel("增益 Mg", fontsize=11)
        ax.tick_params(labelsize=10)

        nan_y = np.full_like(self.fn_curve, np.nan)

        # --- 9 条参考 Q 曲线（不同颜色细线） ---
        cmap = matplotlib.colormaps["tab10"]
        self.hFamily = []
        for i, q in enumerate(Q_FAMILY):
            (line,) = ax.plot(
                self.fn_curve, nan_y,
                linewidth=1.35, color=cmap(i % 10), label=f"Q = {q:g}",
            )
            self.hFamily.append(line)

        # --- 当前 Q 曲线：黑色粗线 ---
        (self.hCurrent,) = ax.plot(
            self.fn_curve, nan_y, color="black", linewidth=2.8,
            label="当前 Q 曲线",
        )

        # --- 阻容分界线（∠Zin = 0，解析边界 Mb(fn)，仅依赖 K=Lm/Lr） ---
        # 边界从 fnp = 1/sqrt(1+K)（此时 Mb→+∞）延伸到 fn→1−。
        # 用相对容差避开奇点处的 inf，超出 ylim 的部分由绘图后端直接裁剪，
        # 不修改数学模型。详见 llc_model.boundary_gain / q_boundary_for_fn。
        fm0 = fn_parallel(DEFAULT_K)
        fb_grid = np.linspace(fm0 * (1.0 + 1e-6), 1.0 - 1e-6, 420)
        (self.hBoundary,) = ax.plot(
            fb_grid, boundary_gain(fb_grid, DEFAULT_K),
            color="darkslategray", linestyle=(0, (7, 4)), linewidth=2.0,
            alpha=0.85, zorder=2.6, label="阻容分界线  ∠Zin = 0",
        )
        self._boundary_grid = fb_grid

        # --- 三条竖线（只创建一次，后续改 xdata） ---
        self.hFnpLine = ax.axvline(
            fn_parallel(DEFAULT_K), color="tab:red",
            linestyle="--", linewidth=1.4, zorder=2,
        )
        self.hFnrLine = ax.axvline(
            fn_series(), color="tab:blue",
            linestyle="--", linewidth=1.4, zorder=2,
        )
        self.hWorkLine = ax.axvline(
            DEFAULT_FN, color="dimgray",
            linestyle=":", linewidth=1.6, zorder=2,
        )

        # --- 竖线文字标签（只创建一次，后续改位置） ---
        xtrans = ax.get_xaxis_transform()
        self.txtFnp = ax.text(
            fn_parallel(DEFAULT_K), 0.30, " fnp", color="tab:red",
            fontsize=10, rotation=90, va="bottom", ha="left",
            transform=xtrans, zorder=5,
        )
        self.txtFnr = ax.text(
            1.0, 0.30, " fnr=1", color="tab:blue",
            fontsize=10, rotation=90, va="bottom", ha="left",
            transform=xtrans, zorder=5,
        )
        self.txtWork = ax.text(
            DEFAULT_FN, 0.97, " 当前 fn", color="dimgray",
            fontsize=10, rotation=90, va="top", ha="left",
            transform=xtrans, zorder=5,
        )

        # --- 四种特征点标记（不同图案，便于图例区分） ---
        (self.hFnpPoint,) = ax.plot(
            [], [], linestyle="none", marker="o", markersize=9,
            markerfacecolor="none", markeredgewidth=1.9,
            color="tab:red", label="○ 当前 Q 曲线的并联谐振点 fnp", zorder=6,
        )
        (self.hFnrPoint,) = ax.plot(
            [], [], linestyle="none", marker="s", markersize=9,
            markerfacecolor="none", markeredgewidth=1.9,
            color="tab:blue", label="□ 当前 Q 曲线的串联谐振点 fnr=1", zorder=6,
        )
        (self.hPeakPoint,) = ax.plot(
            [], [], linestyle="none", marker="^", markersize=10,
            markerfacecolor="none", markeredgewidth=2.0,
            color="tab:green", label="△ 当前 Q 曲线的增益峰值", zorder=6,
        )
        (self.hWorkPoint,) = ax.plot(
            [], [], linestyle="none", marker="D", markersize=9,
            markerfacecolor="none", markeredgewidth=2.0,
            color="black", label="◇ 当前归一化频率工作点 fn", zorder=7,
        )

        self._legend_handles = [
            *self.hFamily, self.hCurrent, self.hBoundary,
            self.hFnpPoint, self.hFnrPoint, self.hPeakPoint, self.hWorkPoint,
        ]
        # ---- 统计计数器（供回归测试断言，不影响性能） ----
        self.stats = {"family": 0, "current": 0, "peak": 0, "legend": 0, "boundary": 0}
        self.legend = None
        self._make_legend()
        # 图例中"当前 Q 曲线"对应的文本对象（hFamily 之后的第 1 项）
        self._legend_q_text = self.legend.get_texts()[len(self.hFamily)]

        self.figure.tight_layout()

        # ---- 内部状态缓存 ----
        self._peak = (float("nan"), float("nan"))
        # 工作区域（∠Zin 判据）与固定 K、Q 下的边界交点
        self._region = "inductive"
        self._fn_boundary = float("nan")
        self._mboundary = float("nan")

    # ------------------------------------------------------------------
    def _make_legend(self) -> None:
        """重建图例。句柄列表固定，只有当前 Q 的文本会变化。"""
        labels = [h.get_label() for h in self._legend_handles]
        self.legend = self.ax.legend(
            self._legend_handles, labels,
            loc="upper right", ncol=2, fontsize=8.5,
            framealpha=0.9, borderpad=0.5, labelspacing=0.35,
        )
        self.stats["legend"] += 1

    def _update_legend_q(self, q_cur: float) -> None:
        """原地更新图例中当前 Q 的文本，不重建图例。"""
        new_label = f"当前 Q 曲线：Q={q_cur:.4f}"
        if self.hCurrent.get_label() != new_label:
            self.hCurrent.set_label(new_label)
            if self.legend is not None:
                try:
                    self._legend_q_text.set_text(new_label)
                except (AttributeError, IndexError):  # pragma: no cover
                    self._make_legend()

    # ------------------------------------------------------------------
    def _compute_family(self, k_ratio: float) -> None:
        """重新计算 9 条固定参考 Q 曲线（仅 K=Lm/Lr 改变时需要）。"""
        for line, q in zip(self.hFamily, Q_FAMILY):
            line.set_ydata(
                llc_gain_from_parts(self.fn_curve, self.fn2, self.fn2m1, k_ratio, q)
            )
        self.stats["family"] += 1

    def _compute_boundary(self, k_ratio: float) -> None:
        """重新计算阻容分界线（仅 K=Lm/Lr 改变时需要；边界不依赖 Q）。"""
        fm0 = fn_parallel(k_ratio)
        fb_grid = np.linspace(fm0 * (1.0 + 1e-6), 1.0 - 1e-6, 420)
        self.hBoundary.set_data(fb_grid, boundary_gain(fb_grid, k_ratio))
        self.stats["boundary"] += 1

    def _compute_current(self, k_ratio: float, q: float) -> np.ndarray:
        """重新计算当前 Q 黑色曲线并搜索峰值。返回当前曲线 y 数据。"""
        M_cur = llc_gain_from_parts(self.fn_curve, self.fn2, self.fn2m1, k_ratio, q)
        self.hCurrent.set_ydata(M_cur)
        self.stats["current"] += 1
        self._peak = find_peak(self.fn_curve, M_cur)
        self.stats["peak"] += 1
        return M_cur

    # ------------------------------------------------------------------
    def _apply_ylim(self, y_max: float) -> None:
        self.ax.set_ylim(0.0, y_max)

    def _update_work_point(self, k_ratio: float, q: float, fn_work: float) -> float:
        """只移动当前工作点竖线与标记（fn 改变时的轻量更新）。返回 M(fn)。

        同时依据 Im(Zin) 的符号判定工作区域，并计算该 K、Q 下增益曲线
        与阻容边界的交点频率。区域判据见 :func:`llc_model.input_region`。
        """
        Mwork = float(llc_gain(fn_work, k_ratio, q))
        self.hWorkLine.set_xdata([fn_work, fn_work])
        self.hWorkPoint.set_data([fn_work], [Mwork])
        self.txtWork.set_x(fn_work)
        self._region = input_region(fn_work, k_ratio, q)
        fb = boundary_frequency(k_ratio, q)
        self._fn_boundary = fb
        self._mboundary = float(llc_gain(fb, k_ratio, q))
        return Mwork

    def _update_resonance_points(self, k_ratio: float, q: float) -> tuple:
        """更新 fnp / fnr 竖线、文字标签与两种谐振点标记。"""
        fnp = fn_parallel(k_ratio)
        fnr = fn_series()
        Mp = float(llc_gain(fnp, k_ratio, q))
        Mr = float(llc_gain(fnr, k_ratio, q))
        self.hFnpLine.set_xdata([fnp, fnp])
        self.hFnrLine.set_xdata([fnr, fnr])
        self.txtFnp.set_x(fnp)
        self.txtFnr.set_x(fnr)
        self.hFnpPoint.set_data([fnp], [Mp])
        self.hFnrPoint.set_data([fnr], [Mr])
        return fnp, Mp, fnr, Mr

    def _update_peak_point(self) -> None:
        fn_peak, m_peak = self._peak
        if np.isfinite(fn_peak) and np.isfinite(m_peak):
            self.hPeakPoint.set_data([fn_peak], [m_peak])
        else:
            self.hPeakPoint.set_data([], [])

    def _collect_values(self, k_ratio, q, fn_work, fnp, Mp, fnr, Mr, Mwork,
                        fr_khz, y_max) -> dict:
        fn_peak, m_peak = self._peak
        return {
            "K": k_ratio, "Q": q, "fn": fn_work, "Mfn": Mwork,
            "fnp": fnp, "Mfnp": Mp, "fnr": fnr, "Mfnr": Mr,
            "fn_peak": fn_peak, "Mpeak": m_peak, "fr_khz": fr_khz,
            "ymax": y_max,
            "region": self._region,
            "fn_boundary": self._fn_boundary,
            "M_boundary": self._mboundary,
        }

    # ------------------------------------------------------------------
    # 公开增量接口
    # ------------------------------------------------------------------
    def refresh(self, k: bool = False, q: bool = False, fn: bool = False,
                fr: bool = False, ylim: bool = False,
                k_ratio: float = DEFAULT_K, Q: float = 0.5,
                fn_work: float = DEFAULT_FN, fr_khz: float = 124.4,
                y_max: float = DEFAULT_YMAX) -> dict:
        """按 dirty flag 只执行必要的计算与重绘。

        参数
        ----
        k   : 需要重算固定参考 Q 曲线族（K=Lm/Lr 改变）+ 当前 Q 曲线等
        q   : 只需要重算当前 Q 曲线（固定参考曲线族不重算）
        fn  : 只移动工作点，不重算任何整条曲线、不搜峰值、不重建图例
        fr  : 只影响实际频率换算文本，不重算归一化曲线
        ylim: 只更新纵轴上限

        返回与 :meth:`update` 相同的关键数值字典。
        """
        if k:
            # 只要 K=Lm/Lr 变了，固定族、当前曲线、边界、谐振点、峰值、工作点全都要
            self._compute_family(k_ratio)
            self._compute_boundary(k_ratio)
            self._compute_current(k_ratio, Q)
            self._update_peak_point()
            fnp, Mp, fnr, Mr = self._update_resonance_points(k_ratio, Q)
            Mwork = self._update_work_point(k_ratio, Q, fn_work)
            self._update_legend_q(Q)
            if ylim:
                self._apply_ylim(y_max)
            return self._collect_values(
                k_ratio, Q, fn_work, fnp, Mp, fnr, Mr, Mwork, fr_khz, y_max)

        if q:
            # Q 改变：只重算当前黑色曲线 + 峰值 + 谐振/工作点 + 图例文本
            self._compute_current(k_ratio, Q)
            self._update_peak_point()
            fnp, Mp, fnr, Mr = self._update_resonance_points(k_ratio, Q)
            Mwork = self._update_work_point(k_ratio, Q, fn_work)
            self._update_legend_q(Q)
            if ylim:
                self._apply_ylim(y_max)
            return self._collect_values(
                k_ratio, Q, fn_work, fnp, Mp, fnr, Mr, Mwork, fr_khz, y_max)

        if fn:
            # fn 改变：只移动工作点竖线/标记/文字
            fnp = fn_parallel(k_ratio)
            fnr = fn_series()
            Mp = float(llc_gain(fnp, k_ratio, Q))
            Mr = float(llc_gain(fnr, k_ratio, Q))
            Mwork = self._update_work_point(k_ratio, Q, fn_work)
            if ylim:
                self._apply_ylim(y_max)
            return self._collect_values(
                k_ratio, Q, fn_work, fnp, Mp, fnr, Mr, Mwork, fr_khz, y_max)

        if ylim:
            self._apply_ylim(y_max)

        # fr 或仅文本更新：不触碰任何曲线
        fnp = fn_parallel(k_ratio)
        fnr = fn_series()
        Mp = float(llc_gain(fnp, k_ratio, Q))
        Mr = float(llc_gain(fnr, k_ratio, Q))
        Mwork = float(llc_gain(fn_work, k_ratio, Q))
        self._region = input_region(fn_work, k_ratio, Q)
        fb = boundary_frequency(k_ratio, Q)
        self._fn_boundary = fb
        self._mboundary = float(llc_gain(fb, k_ratio, Q))
        return self._collect_values(
            k_ratio, Q, fn_work, fnp, Mp, fnr, Mr, Mwork, fr_khz, y_max)

    def update(self, k_ratio: float, q_cur: float, fn_work: float,
               fr_khz: float, y_max: float) -> dict:
        """全量刷新（等价于 ``refresh(k=True, q=True, fn=True, ...)``）。

        保留该接口以兼容旧调用方与既有测试；交互路径应改用
        :meth:`refresh` 的增量接口。
        """
        return self.refresh(
            k=True, q=True, fn=True, fr=True, ylim=True,
            k_ratio=k_ratio, Q=q_cur, fn_work=fn_work,
            fr_khz=fr_khz, y_max=y_max)

    def artist_census(self) -> dict:
        """统计坐标轴上的图形对象数量，用于回归测试。"""
        ax = self.ax
        return {
            "lines": len(ax.lines),
            "texts": len(ax.texts),
            "collections": len(ax.collections),
            "patches": len(ax.patches),
            "legends": len(
                [c for c in ax.get_children() if c.__class__.__name__ == "Legend"]
            ),
        }


def format_result_text(v: dict) -> str:
    """根据关键数值字典生成右侧结果区文本。"""
    fr_khz = v["fr_khz"]
    fn_peak = v["fn_peak"]
    fp_khz = v["fnp"] * fr_khz
    fs_khz = v["fn"] * fr_khz
    fpeak_khz = fn_peak * fr_khz if np.isfinite(fn_peak) else float("nan")

    region_label = {
        "inductive": "感性区（∠Zin > 0）",
        "capacitive": "容性区（∠Zin < 0）",
        "boundary": "阻容边界（∠Zin ≈ 0）",
    }.get(v["region"], v["region"])

    return "\n".join([
        "【当前可调参数】",
        f"  K    = {v['K']:.5f}",
        f"  Q    = {v['Q']:.5f}",
        f"  fn   = {v['fn']:.5f}",
        f"  M(fn)= {v['Mfn']:.5f}",
        f"  fs   = {fs_khz:.3f} kHz",
        "",
        "【工作区域】",
        f"  当前 fn 所在：{region_label}",
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
    ])