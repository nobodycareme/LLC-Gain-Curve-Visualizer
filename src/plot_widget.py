# -*- coding: utf-8 -*-
"""轻量级 LLC 增益曲线绘图控件（PySide6 QWidget + QPainter，无 Matplotlib/NumPy）。

设计目标
--------
* 完全不 import ``matplotlib`` / ``numpy``，从而大幅缩小 EXE、加快冷启动；
* 纯 Python 数学层 :mod:`llc_py` 完成全部 LLC 计算；
* 复刻 :mod:`llc_plot` 的**全部可见功能**：参考 Q 曲线族、当前 Q 曲线、
  阻容分界线（∠Zin=0）、fnp/fnr/工作点竖线与标记、增益峰值、log 横轴、
  线性纵轴、网格、**自适应图例**、中文标签、尺寸自适应、High-DPI、导出 PNG；
* 保持与 :class:`llc_plot.GainPlot` 相同的**增量刷新契约**（``refresh``/``update``，
  dirty flag 增量），以便 :mod:`main` 可直接切换而无需改交互逻辑。

实时交互性能（分层缓存架构）
----------------------------
绘图分成三层：

* **Layer A（Static / 基底）**：背景、坐标轴、刻度、主/次网格、参考 Q 曲线族、
  阻容分界线、fnp/fnr 竖线与标记、峰值标记、图例。渲染进一张 ``QPixmap``，
  只有在 **K / plot 尺寸 / ymax / Q** 真正变化时才重建。
* **Layer B（Semi-Dynamic / 当前 Q）**：当前 Q 曲线 + 峰值，缓存为 ``QPainterPath``；
  Q 变化时只重建这一条路径并贴回基底，不动参考族/边界。
* **Layer C（Dynamic Overlay）**：当前 fn 竖线、工作点、工作点文字、Hover 高亮点
  与 Tooltip。每帧绘制，极其轻量。

* **QPainterPath 缓存**：所有曲线都已固化为 ``QPainterPath``，paintEvent 只
  重放缓存路径，绝不逐点重建。
* **fn 变化**：只更新 Overlay（工作点 + fn 竖线），零路径重建。
* **Q 变化**：只重建当前 Q 一条路径，零参考族/边界重建。
* **K 变化**：重建参考族 + 边界 + 当前 Q 路径。
* **滑块释放**：不再全量 dirty，只刷新尚未 flush 的最后一个值（见 :mod:`main`）。

曲线裁剪
--------
采用 ``painter.setClipRect(plot_rect)`` 原生裁剪：曲线超过 ymax 的部分由 Qt
裁掉，**不会通过修改数据造成"断线"**。

Hover Inspector
---------------
鼠标悬停任意增益曲线即显示精确 LLC 参数。命中检测使用**数学公式直接计算**
（每条候选曲线只算 1 个标量点），不做 3000 采样点遍历。行为：
* 反变换 ``pixel_to_fn`` 与正变换 ``fn_to_pixel`` 互为一致；
* 候选 = 9 条参考 Q + 当前 Q + 阻容分界线，按屏幕像素距离选最近；
* 距离几乎相同（< 1px）时 tie-break：当前 Q > 阻容分界线 > 参考 Q；
* 容差 8 CSS 像素（逻辑坐标，天然兼容 High-DPI）；
* 区域判据来自 ``input_region``（∠Zin），不从图形两侧猜测。

对象/缓存不增长
--------------
数据数组只在构造函数中分配一次；``refresh`` 只改写已有列表元素，绝不 append
到长期数组、绝不新增绘制对象。缓存路径/基底 pixmap 均原地替换，数量恒定。
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QEvent  # noqa: F401
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import QWidget

# 引入纯 Python 数学层（无 numpy / matplotlib）
from llc_py import (  # noqa: E402
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
    q_boundary_for_fn,
)

__all__ = ["GainPlotWidget", "FAMILY_COLORS"]

#: 参考 Q 曲线族配色（近似 tab10，前 9 色）
FAMILY_COLORS = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22",
]
CURRENT_COLOR = "#111111"
#: 阻容分界线：高饱和品红，白底高对比，明显区别于黑当前 Q / 红 fnp / 蓝 fnr。
BOUNDARY_COLOR = "#D000C8"
BOUNDARY_LABEL_COLOR = "#A00098"
FNP_COLOR = "#d62728"
FNR_COLOR = "#1f4fd0"
WORK_COLOR = "#6e6e6e"
#: 工程范围带配色：M 范围用低饱和青绿，fn 范围用暖橙（均半透明，避免遮挡曲线）。
M_BAND_COLOR = "#2e8c50"
FN_BAND_COLOR = "#e6951e"

#: Y 轴 nice-number 候选（raw_step = ymax/目标刻度数）
_NICE_MULTS = (1.0, 2.0, 2.5, 5.0, 10.0)

#: Hover 命中容差（CSS/逻辑像素，天然兼容 High-DPI）
HOVER_TOL_PX = 8.0
#: 多曲线几乎重合（< 1px 差）时的优先级：数值越小越优先
_HOVER_PRIORITY = {"current": 0, "boundary": 1, "family": 2}

# ---- Hover 工程信息卡配色（需求 4：高对比、清晰层级，但不花哨） ----
# 与曲线的 Q family 配色体系完全无关，仅作用于 Hover 卡片本身。
HP_CARD_BG    = QColor(255, 255, 255, 246)   # 近白略灰，基本不透明
HP_CARD_LINE  = QColor(148, 163, 184)        # #94A3B8 边框
HP_HEADER     = QColor(37, 99, 235)          # #2563EB 标题
HP_TEXT       = QColor(31, 41, 55)           # #1F2937 正文
HP_BOLD       = QColor(15, 23, 42)           # 近黑，fn/M 醒目
HP_SEC        = QColor(100, 116, 139)        # #64748B 次要
HP_BADGE_IN   = QColor(21, 128, 61)          # #15803D 感性(蓝绿)
HP_BADGE_CAP  = QColor(217, 119, 6)          # #D97706 容性(橙)


def _hex(color: str) -> QColor:
    return QColor(color)


def _fmt_bound_val(x: float) -> str:
    """边界量（可能 ±inf/NaN）的展示格式"""
    if x is None:
        return "—"
    x = float(x)
    if math.isnan(x):
        return "无定义"
    if math.isinf(x):
        return "∞"
    return f"{x:.4f}"


def _fmt_freq(hz: float) -> str:
    """频率自动 Hz / kHz / MHz 显示"""
    if hz is None or math.isnan(hz) or math.isinf(hz):
        return "∞"
    if hz >= 1.0e6:
        return f"{hz / 1.0e6:.3f} MHz"
    if hz >= 1.0e3:
        return f"{hz / 1.0e3:.3f} kHz"
    return f"{hz:.1f} Hz"


def _path_y_at(path, x: float):
    """从 QPainterPath 折线中读取 x 处的插值 Y（当前 Q 曲线的实际渲染像素 Y）。"""
    n = path.elementCount()
    prev = None
    for i in range(n):
        e = path.elementAt(i)
        if e.isMoveTo() or e.isLineTo():
            pt = (e.x, e.y)
            if prev is not None:
                x0, y0 = prev
                x1, y1 = pt
                if x0 <= x <= x1 or x1 <= x <= x0:
                    if x1 == x0:
                        return y1
                    t = (x - x0) / (x1 - x0)
                    return y0 + t * (y1 - y0)
            prev = pt
    return None


_REGION_LABEL = {
    "inductive": "感性区（∠Zin > 0）",
    "capacitive": "容性区（∠Zin < 0）",
    "boundary": "阻容边界（∠Zin ≈ 0）",
}


class GainPlotWidget(QWidget):
    """QPainter 版增益曲线控件。

    ``stats`` 与 :class:`llc_plot.GainPlot` 语义一致：记录各类计算次数，
    供回归测试断言"增量更新正确性"。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumSize(560, 420)
        self.setMouseTracking(True)

        # ---- 数学数据：只在构造时分配一次 ----
        self.fn_curve = make_fn_curve()
        self.fn2 = [f * f for f in self.fn_curve]
        self.fn2m1 = [f2 - 1.0 for f2 in self.fn2]
        n = len(self.fn_curve)
        nan = float("nan")

        self.family_y = [[nan] * n for _ in Q_FAMILY]
        self.current_y = [nan] * n
        # ---- 拖动 preview 独立数据缓冲（需求 1：绝不污染正式 family_y） ----
        # preview 用降采样点独立数组，K 拖动时只填充这些点；正式 family_y 保持
        # full-resolution 纯净。松开 K 后 _compute_family(full) 一次完整重算，
        # 从数据层面杜绝"新旧 K 值周期交错"导致的彩色色带。
        self.preview_step = 4
        self.family_preview_x = self.fn_curve[::self.preview_step]
        self.fn2_p = self.fn2[::self.preview_step]
        self.fn2m1_p = self.fn2m1[::self.preview_step]
        self.family_preview_y = [[nan] * len(self.family_preview_x) for _ in Q_FAMILY]
        self.boundary_x: list = []
        self.boundary_y: list = []
        #: 阻容分界线竖直段（fn=1、M=1→0），见 _compute_boundary
        self.boundary_vline: tuple = (1.0, 1.0)

        # ---- 逐参数缓存 ----
        self.K = float(DEFAULT_K)
        self.Q = 0.5
        self.fn_work = float(DEFAULT_FN)
        self.fr_khz = 124.4
        self.ymax = float(DEFAULT_YMAX)

        self.peak = (float("nan"), float("nan"))
        self.region = "inductive"
        self.fn_boundary = float("nan")
        self.mboundary = float("nan")

        # fnp/fnr 竖线与工作点
        self.fnp = fn_parallel(self.K)
        self.fnr = fn_series()

        self.stats = {"family": 0, "current": 0, "peak": 0, "boundary": 0}

        # ---- Layer 缓存（路径 / 基底 pixmap / 重建计数） ----
        self._base_pixmap: QPixmap | None = None
        self._base_dirty = True
        self._base_key_size = (-1, -1)
        self._base_key_dpr = 0.0

        #: 真正不随 K 变化的背景层（白底+网格+坐标轴+刻度文字）独立 pixmap。
        #: K 拖动时基底只合成这张缓存 + K 依赖曲线，省去重画网格/文字。
        self._backdrop_pixmap: QPixmap | None = None
        self._backdrop_key = (-1, -1, None)

        # 路径缓存（含其构建键，判断是否需要重建）
        self._fam_paths: list = []
        self._boundary_path: QPainterPath | None = None
        self._boundary_vline_path: QPainterPath | None = None
        self._cur_path: QPainterPath | None = None
        self._path_rect: QRectF | None = None
        self._path_keys = {"K": None, "Q": None}

        #: 统一几何版本号：任何会改变 plot_rect 的状态（尺寸/图例可见性/ymax/字号）
        #: 都递增它。所有路径与 pixmap 缓存键必须包含它，杜绝"旧几何路径 + 新几何
        #: 工作点"的错位（BUG1 根因）。
        self._geom_gen = 0

        #: 隐藏图层 lazy 重建标记（需求 6.1）：参考 Q / 阻容分界线隐藏时，
        #: K 拖动期间跳过其显示数据与路径重建，只置 dirty；重新打开或最终刷新时
        #: 才 lazy rebuild。数学判据（fn_boundary / input_region）不受影响。
        self._family_dirty = False
        self._boundary_dirty = False

        #: Layer B（当前 Q 曲线 + fnp/fnr/峰值 marker）独立 pixmap。
        #: 只随 Q/K/尺寸/字号变化重建；fn 拖动完全复用，从 repaint 中省掉重画
        #: 当前曲线的 1500 点 drawPath 成本。
        self._semi_pixmap: QPixmap | None = None
        self._semi_key = None

        #: 各层重建次数（供回归测试断言"只重建必要层"）
        self.rebuild = {
            "family_path": 0, "boundary_path": 0,
            "current_path": 0, "base": 0,
        }

        #: fn_curve 显示采样点（索引 + 像素 X）缓存：同一 rect 下所有 fn_curve
        #: 路径共享，K/Q 变化时无需逐点重算 log10 映射。
        self._disp_idx: list = []
        self._disp_px: list = []
        self._disp_key = None

        # ---- Hover 状态 ----
        self._hover = None          # 命中的曲线信息 dict 或 None
        self._hover_rect: QRect | None = None
        self._hover_mouse = None

        # ---- 显示状态（与数学状态分离，见需求二十七） ----
        # 仅影响"画不画/图例/Hover"，绝不触发任何无关数学重算。
        self.show_reference = True   # 预设参考 Q 曲线族
        self.show_boundary = True    # 阻容分界线 ∠Zin=0
        self.show_m_range = False    # M_req_min ~ M_req_max 水平范围带
        self.show_fn_range = False   # fn_min ~ fn_max 竖直范围带
        # 工程范围带的数值（由设计层写入；仅显示，不影响数学）
        self.m_req_min = float("nan")
        self.m_req_max = float("nan")
        self.fn_min_band = float("nan")
        self.fn_max_band = float("nan")

        # ---- 拖动 preview 模式（需求 6.4） ----
        # sliderPressed 置 True：参考族用降采样（~750 点）绘制，当前曲线保持全精度；
        # sliderReleased 置 False：恢复全精度并做一次最终路径重建。
        # 数学（M(fn)/peak/fn_boundary/root solve）不受 preview 影响。
        self._preview = False

        # ---- 性能采集（env 开关，默认关闭；供回归/报告用） ----
        self._collect_perf = os.environ.get("LLC_PERF_DETAIL", "") in (
            "1", "true", "on")
        self._paint_ms: list = []
        self._hover_ms: list = []
        import time as _t
        self._time = _t

        # -- 初始数据（等价一次全量刷新） --
        self._compute_family(self.K)
        self._compute_boundary(self.K)
        self._compute_current(self.K, self.Q)
        self._update_region()

    # ------------------------------------------------------------------
    # 数学计算（只改列表元素，不增长）
    # ------------------------------------------------------------------
    def _compute_family(self, k_ratio: float, preview: bool = False) -> None:
        """参考 Q 曲线族显示数据。

        ``preview=True``：**只**写入独立的 ``family_preview_y`` 降采样数组，
        绝不触碰 full-resolution 的 ``family_y``（需求 1 数据隔离）。
        ``preview=False``：完整重算正式 ``family_y``（3000 点/条）。
        """
        if preview:
            self._compute_family_preview(k_ratio)
            return
        for y, q in zip(self.family_y, Q_FAMILY):
            new = llc_gain_from_parts(self.fn_curve, self.fn2, self.fn2m1, k_ratio, q)
            y[:] = [float(v) for v in new]
        self.stats["family"] += 1
        self.rebuild["family_path"] += 1  # 数据变了，路径需重建
        self._base_dirty = True

    def _compute_family_preview(self, k_ratio: float) -> None:
        """K 拖动 preview：只填充独立降采样数组 ``family_preview_y``。

        数据与 ``family_y`` 完全分离，从源头杜绝新旧 K 值交错污染。
        ``family_preview_x`` / ``fn2_p`` / ``fn2m1_p`` 在构造时按同一 ``preview_step``
        采样，数学公式与全精度一致（仅点数 3000→750）。
        """
        for y, q in zip(self.family_preview_y, Q_FAMILY):
            new = llc_gain_from_parts(
                self.family_preview_x, self.fn2_p, self.fn2m1_p, k_ratio, q)
            y[:] = [float(v) for v in new]
        self.stats["family"] += 1
        self.rebuild["family_path"] += 1  # 数据变了，路径需重建
        self._base_dirty = True

    def _compute_current(self, k_ratio: float, q: float) -> None:
        new = llc_gain_from_parts(self.fn_curve, self.fn2, self.fn2m1, k_ratio, q)
        self.current_y[:] = [float(v) for v in new]
        self.peak = find_peak(self.fn_curve, self.current_y)
        self.stats["current"] += 1
        self.stats["peak"] += 1
        self.rebuild["current_path"] += 1  # 数据变了，路径需重建
        # 基底 pixmap 不依赖 Q：Q 是否触发基底重建由调用方决定（K 路径置位，Q 路径不置位）

    def _compute_boundary(self, k_ratio: float) -> None:
        """阻容分界线显示数据（∠Zin=0 弯曲段 + fn=1 竖直段）。

        弯曲段从 fnp 起，**准确连接到 (fn=1, M=1)**（不再留 1e-6 缺口，需求 3.2B）；
        竖直段为 fn=1、M=1→0（需求 3.2C），与弯曲段同风格、同一图例条目。
        """
        fm0 = fn_parallel(k_ratio)
        step = (1.0 - fm0) / 419
        xs = [fm0 * (1.0 + 1e-6) + step * i for i in range(420)]
        xs[-1] = 1.0
        ys = boundary_gain(xs, k_ratio)
        if not self.boundary_x:
            self.boundary_x = [float(v) for v in xs]
            self.boundary_y = [float(v) for v in ys]
        else:
            self.boundary_x[:] = [float(v) for v in xs]
            self.boundary_y[:] = [float(v) for v in ys]
        # 竖直段：fn=1，M 从 1 到 0（M=0 即绘图区底边）
        self.boundary_vline = (1.0, 1.0)
        self.stats["boundary"] += 1
        self.rebuild["boundary_path"] += 1  # 数据变了，路径需重建
        self._base_dirty = True

    def _update_region(self) -> None:
        self.region = input_region(self.fn_work, self.K, self.Q)
        fb = boundary_frequency(self.K, self.Q)
        self.fn_boundary = fb
        self.mboundary = float(llc_gain(fb, self.K, self.Q))

    # ------------------------------------------------------------------
    # 增量刷新接口（与 llc_plot.GainPlot.refresh 契约一致）
    # ------------------------------------------------------------------
    def refresh(self, k: bool = False, q: bool = False, fn: bool = False,
                fr: bool = False, ylim: bool = False,
                k_ratio: float = DEFAULT_K, Q: float = 0.5,
                fn_work: float = DEFAULT_FN, fr_khz: float = 124.4,
                y_max: float = DEFAULT_YMAX) -> dict:
        # 任何参数变化都会让旧 hover 失效
        if k or q or fn or fr or ylim:
            self._clear_hover_state()

        was_ylim = self.ymax
        if k:
            self.K = float(k_ratio)
            self.Q = float(Q)
            self.fn_work = float(fn_work)
            self.fr_khz = float(fr_khz)
            if ylim:
                self.ymax = float(y_max)
            self.fnp = fn_parallel(self.K)
            self.fnr = fn_series()
            # 需求 6.1：隐藏图层不持续做显示用重计算，只记录 dirty，等重新打开
            # 或最终刷新再 lazy rebuild。数学判据（fn_boundary / region）始终计算。
            if self.show_reference:
                self._compute_family(self.K, self._preview)
            else:
                self._family_dirty = True
            if self.show_boundary:
                self._compute_boundary(self.K)
            else:
                self._boundary_dirty = True
            self._compute_current(self.K, self.Q)
            self._update_region()
            if was_ylim != self.ymax or ylim:
                self._base_dirty = True
            self._invalidate_geometry()
            self.update()
            return self._values()

        if q:
            self.K = float(k_ratio)
            self.Q = float(Q)
            self.fn_work = float(fn_work)
            self.fr_khz = float(fr_khz)
            if ylim:
                self.ymax = float(y_max)
            self.fnp = fn_parallel(self.K)
            self.fnr = fn_series()
            self._compute_current(self.K, self.Q)
            self._update_region()
            if was_ylim != self.ymax:
                self._base_dirty = True
            self._invalidate_current_geometry()
            self.update()
            return self._values()

        if fn:
            self.K = float(k_ratio)
            self.Q = float(Q)
            self.fn_work = float(fn_work)
            self.fr_khz = float(fr_khz)
            if ylim:
                self.ymax = float(y_max)
            self.fnp = fn_parallel(self.K)
            self.fnr = fn_series()
            self._update_region()
            if was_ylim != self.ymax:
                self._base_dirty = True
            self.update()
            return self._values()

        # fr / ylim / 纯文本更新：只更新元数据与显示范围
        self.K = float(k_ratio)
        self.Q = float(Q)
        self.fn_work = float(fn_work)
        self.fr_khz = float(fr_khz)
        if ylim:
            self.ymax = float(y_max)
        self.fnp = fn_parallel(self.K)
        self.fnr = fn_series()
        self._update_region()
        if was_ylim != self.ymax:
            self._base_dirty = True
        self.update()
        return self._values()

    def update_full(self, k_ratio, q_cur, fn_work, fr_khz, y_max) -> dict:
        """全量刷新（兼容旧调用方）。"""
        return self.refresh(
            k=True, q=True, fn=True, fr=True, ylim=True,
            k_ratio=k_ratio, Q=q_cur, fn_work=fn_work,
            fr_khz=fr_khz, y_max=y_max)

    def set_display_state(self, *, show_reference=None, show_boundary=None,
                          show_m_range=None, show_fn_range=None,
                          m_req_min=None, m_req_max=None,
                          fn_min=None, fn_max=None) -> bool:
        """仅更新**显示状态**，绝不触发任何无关数学重算（需求八/二十七/二十八）。

        切换某个显示图层（参考 Q / 阻容边界 / M 范围 / fn 范围）只重渲染基底
        与图例条带：数据（family_y / boundary_y / fn_boundary / region 等）被原样
        复用。``fn_boundary`` 始终继续计算（显示状态不影响数学）。

        返回是否有任何显示参数实际变化。
        """
        changed = False

        # 逐项比较并赋值；重新打开隐藏图层时 lazy rebuild 其显示数据（需求 6.1）
        if show_reference is not None and bool(show_reference) != self.show_reference:
            self.show_reference = bool(show_reference); changed = True
            if self.show_reference and self._family_dirty:
                self._compute_family(self.K)
                self._family_dirty = False
        if show_boundary is not None and bool(show_boundary) != self.show_boundary:
            self.show_boundary = bool(show_boundary); changed = True
            if self.show_boundary and self._boundary_dirty:
                self._compute_boundary(self.K)
                self._boundary_dirty = False
        if show_m_range is not None and bool(show_m_range) != self.show_m_range:
            self.show_m_range = bool(show_m_range); changed = True
        if show_fn_range is not None and bool(show_fn_range) != self.show_fn_range:
            self.show_fn_range = bool(show_fn_range); changed = True

        values_changed = False
        if m_req_min is not None and float(m_req_min) != self.m_req_min:
            self.m_req_min = float(m_req_min); values_changed = True
        if m_req_max is not None and float(m_req_max) != self.m_req_max:
            self.m_req_max = float(m_req_max); values_changed = True
        if fn_min is not None and float(fn_min) != self.fn_min_band:
            self.fn_min_band = float(fn_min); values_changed = True
        if fn_max is not None and float(fn_max) != self.fn_max_band:
            self.fn_max_band = float(fn_max); values_changed = True

        if changed or values_changed:
            self._clear_hover_state()
            if changed:
                # 图例可见性变化会改变 plot_rect 几何（图例行数→顶部偏移）。
                # 必须让所有依赖几何的路径/pixmap 失效，否则当前 Q 路径仍按旧几何画，
                # 而工作点按新几何实时计算 → 错位（BUG1）。只重建像素路径/缓存，
                # 不重算任何 LLC 数学数据。
                self._invalidate_geometry()
                self._invalidate_base_only()
            else:
                # 仅 M/fn 范围带数值变化：几何不变，只重画基底带。
                self._base_dirty = True
            self.update()
        return changed or values_changed

    def set_preview(self, preview: bool) -> None:
        """拖动 preview 模式。

        ``True``：参考族使用独立降采样 ``family_preview_y``（见 ``_compute_family_preview``），
        当前曲线保持全精度；``False``：**完整重算一次正式 ``family_y``**（3000 点/条），
        清零/忽略 preview 数据，杜绝新旧 K 值交错（需求 1 彩色色带根因）。
        只影响显示采样，不重算任何其他 LLC 数学数据。
        """
        preview = bool(preview)
        if preview == self._preview:
            return
        self._preview = preview
        if not self._preview:
            # 需求 1：退出 preview 必须重新生成完整 full-resolution family_y，
            # 不能被拖动期间的 partial 数据污染。即使参考族隐藏也重算（一次，廉价）。
            self._compute_family(self.K, preview=False)
        self._path_keys["K"] = None
        self._fam_paths = []
        self._invalidate_base_only()
        self.update()

    def _invalidate_base_only(self) -> None:
        """只作废基底 pixmap 与图例条带，保留所有数学缓存与路径（值未变）。"""
        self._base_pixmap = None
        self._legend_pixmap = None
        self._legend_key = None

    def _invalidate_geometry(self):
        """K / 尺寸 / ymax / 图例可见性变化：所有路径、基底与半动态层作废。

        递增统一几何版本号，确保任何依赖 plot_rect 几何的缓存（当前 Q 路径、
        semi pixmap、基底）都强制重建，与实时计算的工作点严格对齐（BUG1）。
        """
        self._geom_gen += 1
        self._path_rect = None
        self._path_keys = {"K": None, "Q": None}
        self._fam_paths = []
        self._boundary_path = None
        self._boundary_vline_path = None
        self._cur_path = None
        self._base_key_size = (-1, -1)
        self._base_dirty = True
        self._base_pixmap = None
        self._semi_pixmap = None
        self._semi_key = None
        self.rebuild["base"] += 1

    def _invalidate_current_geometry(self):
        """仅 Q 变化：只作废当前 Q 路径与半动态层，绝不动基底 pixmap。

        基底内容（backdrop 网格 + 参考族/边界/fnp·fnr 竖线）全部与 Q 无关，Q 变化
        必须复用原地缓存 base，从而把单帧成本压到"重算当前曲线 + 重放半动态层"，
        消除 Q 拖动卡顿。当前 Q 曲线/标记属于 Layer B，Q 变化重建 semi pixmap
        覆盖到 base 之上，无像素残留。
        """
        if self._path_rect is not None:
            self._path_keys["Q"] = None
            self._cur_path = None
        self._semi_pixmap = None
        self._semi_key = None

    def _values(self) -> dict:
        return {
            "K": self.K, "Q": self.Q, "fn": self.fn_work,
            "Mfn": float(llc_gain(self.fn_work, self.K, self.Q)),
            "fnp": fn_parallel(self.K),
            "Mfnp": float(llc_gain(fn_parallel(self.K), self.K, self.Q)),
            "fnr": fn_series(),
            "Mfnr": float(llc_gain(fn_series(), self.K, self.Q)),
            "fn_peak": self.peak[0], "Mpeak": self.peak[1],
            "fr_khz": self.fr_khz, "ymax": self.ymax,
            "region": self.region,
            "fn_boundary": self.fn_boundary,
            "M_boundary": self.mboundary,
        }

    # ------------------------------------------------------------------
    # 测试辅助（读取当前内存数据）
    # ------------------------------------------------------------------
    def current_data_y(self) -> list:
        return list(self.current_y)

    def family_data_y(self) -> list:
        return [list(y) for y in self.family_y]

    def boundary_data(self) -> tuple:
        return list(self.boundary_x), list(self.boundary_y)

    def legend_entries(self) -> list:
        """返回图例条目列表 ``[(color, width, style, text), ...]``，供测试断言。

        与绘图/Hover 使用同一 visibility state：隐藏层不出现在图例（需求七/八/二十八）。
        核心五项（当前 Q、fnp、fnr=1、工作点 fn、增益峰值）始终保留，禁止隐藏。
        """
        entries = []
        if self.show_reference:
            for q, col in zip(Q_FAMILY, FAMILY_COLORS):
                entries.append((col, 1.2, Qt.SolidLine, f"Q = {q:g}"))
        entries.append((CURRENT_COLOR, 2.6, Qt.SolidLine,
                        f"当前 Q 曲线：Q={self.Q:.4f}"))
        if self.show_boundary:
            entries.append((BOUNDARY_COLOR, 3.2, Qt.DashLine, "阻容分界线"))
        entries.append((FNP_COLOR, 1.2, Qt.SolidLine, "fnp（并联谐振）"))
        entries.append((FNR_COLOR, 1.2, Qt.SolidLine, "fnr=1（串联谐振）"))
        entries.append((CURRENT_COLOR, 1.2, Qt.SolidLine, "△ 增益峰值"))
        entries.append((WORK_COLOR, 1.2, Qt.SolidLine, "◇ 工作点 fn"))
        if self.show_m_range and math.isfinite(self.m_req_min) \
                and math.isfinite(self.m_req_max):
            entries.append((M_BAND_COLOR, 1.2, Qt.SolidLine,
                            f"M 范围  {self.m_req_min:.3f}~{self.m_req_max:.3f}"))
        if self.show_fn_range and math.isfinite(self.fn_min_band) \
                and math.isfinite(self.fn_max_band):
            entries.append((FN_BAND_COLOR, 1.2, Qt.SolidLine,
                            f"fn 范围  {self.fn_min_band:.3f}~{self.fn_max_band:.3f}"))
        return entries

    # ------------------------------------------------------------------
    # 坐标映射（正/反变换互为一致）
    # ------------------------------------------------------------------
    def _map_x(self, fn: float, r: QRectF) -> float:
        log = math.log10(fn)
        lo = math.log10(FN_MIN)
        span = math.log10(FN_MAX) - lo
        return r.left() + (log - lo) / span * r.width()

    def pixel_to_fn(self, x: float, r: QRectF) -> float:
        """像素 X -> fn（``_map_x`` 严格反函数）。"""
        if r.width() <= 0.0:
            return float("nan")
        lo = math.log10(FN_MIN)
        span = math.log10(FN_MAX) - lo
        frac = (x - r.left()) / r.width()
        return float(10.0 ** (lo + frac * span))

    def _map_y(self, m: float, r: QRectF, ymax: float = None) -> float:
        """绘图用映射：夹取到 [0, ymax]，工作点/标记落在图内边缘。"""
        top = float(self.ymax if ymax is None else ymax)
        return r.top() + (top - max(0.0, min(m, top))) / top * r.height()

    def _map_y_full(self, m: float, r: QRectF, ymax: float = None) -> float:
        """命中检测用映射：不夹取（保留真实几何，供像素距离计算）。"""
        top = float(self.ymax if ymax is None else ymax)
        if top <= 0.0:
            return r.top()
        return r.top() + (top - float(m)) / top * r.height()

    # ------------------------------------------------------------------
    # 图例自适应布局
    # ------------------------------------------------------------------
    def _legend_font(self, h: float) -> QFont:
        f = QFont(self.font() or QFont())
        f.setPointSizeF(max(7.0, h / 120.0))
        return f

    def _legend_layout(self, avail_w, widget_h):
        """根据可用宽度动态决定图例列数/行数/行高/每列宽。

        返回 dict：{cols, rows, row_h, col_w, entries, height}
        """
        entries = self.legend_entries()
        font = self._legend_font(widget_h)
        met = QFontMetrics(font)
        pad_x, pad_y = 10, 4
        swatch = 16
        gap = swatch + 10

        widths = [met.horizontalAdvance(txt) for (_, _, _, txt) in entries]
        longest = max(widths)
        n = len(entries)
        avail = max(80.0, avail_w - pad_x * 2)
        cols = max(1, min(n, int(avail / (longest + gap))))
        rows = max(1, math.ceil(n / cols))
        # 行高随设备缩放适当放大，避免 High-DPI 文字烫行
        dpr = self.devicePixelRatioF()
        row_h = met.height() + max(pad_y, int(2 * max(1.0, dpr)))
        height = rows * row_h + pad_y
        return {
            "cols": cols, "rows": rows, "row_h": row_h, "col_w": widths,
            "entries": entries, "height": height, "font": font,
        }

    def _plot_rect(self, w: float, h: float) -> QRectF:
        """绘图区（顶部留出独立图例 band 防止遮挡核心曲线）。"""
        left = 74.0
        right = 26.0
        bottom = 50.0
        avail_w = max(80.0, w - left - right)
        legend = self._legend_layout(avail_w, float(h))
        top = legend["height"] + 8.0
        return QRectF(left, top, avail_w, max(20.0, float(h) - top - bottom))

    # ------------------------------------------------------------------
    # 几何缓存键（BUG1）：任何路径/pixmap 缓存键必须包含它
    # ------------------------------------------------------------------
    def _geom_key(self, r: QRectF):
        """几何相关的缓存键前缀：几何版本 + 绘图区 rect。

        所有依赖坐标映射的缓存（当前 Q 路径 / semi pixmap / 参考族 / 边界路径 /
        显示采样）都必须用本键（或其矩形字段）做键的一部分，从而**无需依赖手动
        失效**：只要 plot_rect 的几何（含图例可见性导致的顶部偏移）有任何变化，
        缓存键就必然不同，杜绝"旧几何曲线 + 新几何工作点"的错位（BUG1 根因）。

        K/Q 不含在内：它们是"数学键"，与"几何键"分开（见需求 6.5）。
        """
        return (self._geom_gen, round(r.left(), 3), round(r.top(), 3),
                round(r.width(), 3), round(r.height(), 3), round(self.ymax, 4))

    # ------------------------------------------------------------------
    # 曲线路径构建（一次构建，供基底渲染与 PNG 复用）
    # ------------------------------------------------------------------
    def _render_step(self, total: int) -> int:
        """显示采样步长：把 N 个数据点降采样为约 1600 个显示点。

        数学精度（峰值/边界/Hover）始终用精确公式，显示采样减少不会影响结果。
        数据数组本身仍保留 3000 点，仅用于路径构建时步进。
        """
        target = 1600
        if total <= target:
            return 1
        return max(1, math.ceil(total / target))

    def _display_sample(self, r: QRectF, step: int):
        """fn_curve 显示采样点缓存：返回 (索引列表, 像素 X 列表)。

        同一 rect + step 下，fn_curve 上所有曲线（家族/当前）的像素 X 完全一致，
        只算一次。``step=1``（边界用 boundary_x 走各自路径）除外。
        """
        key = self._geom_key(r) + (step,)
        if self._disp_idx and self._disp_key == key:
            return self._disp_idx, self._disp_px
        lo = math.log10(FN_MIN)
        span = math.log10(FN_MAX) - lo
        idx: list = []
        px: list = []
        n = len(self.fn_curve)
        cs = max(1, step)
        for i in range(0, n, cs):
            fn = self.fn_curve[i]
            idx.append(i)
            px.append(r.left() + (math.log10(fn) - lo) / span * r.width())
        self._disp_idx = idx
        self._disp_px = px
        self._disp_key = key
        return idx, px

    def _build_curve_path(self, xs, ys, r: QRectF, step: int = 1,
                          disp: tuple | None = None) -> QPainterPath:
        path = QPainterPath()
        started = False
        big = max(40.0, r.height() * 6.0)
        clamp0 = r.top() - big
        clamp1 = r.bottom() + big
        n = len(xs)
        cs = max(1, step)
        if disp is not None:
            # 使用共享的 (索引, 像素X) —— 避免逐点 log10 重算
            d_idx, d_px = disp
            top = float(self.ymax)
            for i, px in zip(d_idx, d_px):
                m = ys[i]
                if m is None or m != m:  # NaN：断开
                    started = False
                    continue
                py = r.top() + (top - float(m)) / top * r.height()
                if py < clamp0 or py > clamp1:
                    py = clamp0 if py < clamp0 else clamp1
                if not started:
                    path.moveTo(px, py)
                    started = True
                else:
                    path.lineTo(px, py)
            return path
        for i in range(0, n, cs):
            fn = xs[i]
            m = ys[i]
            if m is None or m != m:  # NaN：断开
                started = False
                continue
            try:
                px = self._map_x(fn, r)
                py = self._map_y_full(m, r)
            except (ValueError, OverflowError):
                started = False
                continue
            if py < clamp0 or py > clamp1:  # 把远离可视区的巨值夹紧，保持路径有效
                py = clamp0 if py < clamp0 else clamp1
            if not started:
                path.moveTo(px, py)
                started = True
            else:
                path.lineTo(px, py)
        return path

    def _build_boundary_extras(self, r: QRectF) -> None:
        """构建阻容分界线竖直段路径（fn=1、M=1→0）。

        与弯曲段同风格（同一 pen 绘制，见 ``_draw_boundary``），不新增图例条目。
        竖直段不是单值函数 M(fn)，故单独存路径，Hover 用独立几何 hit test
        （需求 3.4），绝不伪造 ``boundary_gain(1)``。
        """
        x = self._map_x(1.0, r)
        y_top = self._map_y_full(1.0, r)
        y_bot = self._map_y_full(0.0, r)
        path = QPainterPath()
        path.moveTo(x, y_top)
        path.lineTo(x, y_bot)
        self._boundary_vline_path = path

    def _ensure_static_paths(self, r: QRectF, preview: bool = False):
        """Layer A 路径：参考族 + 阻容边界（按 K + rect 缓存；Q 不触发重建）。

        需求 6.1：隐藏图层（show_reference / show_boundary 为 False）不构建其
        显示路径，K 拖动期间省去 9 条参考族 + 边界路径的重建成本；重新打开时
        由 ``set_display_state`` 触发 lazy rebuild。
        需求 6.4：``preview=True`` 时参考族路径按 step=4 降采样（~750 点），
        与 ``_compute_family(preview=True)`` 写入的稀疏点严格对应。
        """
        key = (self.K, preview) + self._geom_key(r)
        if self._path_rect != r or self._path_keys["K"] != key:
            if preview:
                # 需求 1：preview 状态用独立降采样数组建路径（其 x 采样为
                # family_preview_x，区别于 fn_curve，故 disp 传 None 逐点映射）。
                if self.show_reference:
                    self._fam_paths = [self._build_curve_path(
                        self.family_preview_x, y, r, 1) for y in self.family_preview_y]
                else:
                    self._fam_paths = []
            else:
                step = self._render_step(len(self.fn_curve))
                disp = self._display_sample(r, step)
                if self.show_reference:
                    self._fam_paths = [self._build_curve_path(
                        self.fn_curve, y, r, step, disp) for y in self.family_y]
                else:
                    self._fam_paths = []
            if self.show_boundary:
                self._boundary_path = self._build_curve_path(
                    self.boundary_x, self.boundary_y, r, 1)
                self._build_boundary_extras(r)
            else:
                self._boundary_path = None
                self._boundary_vline_path = None
            self._path_keys["K"] = key
            self._path_rect = r
        if self._cur_path is None or self._path_keys["Q"] != (self.Q, self.K) + self._geom_key(r):
            step = self._render_step(len(self.fn_curve))
            disp = self._display_sample(r, step)
            self._cur_path = self._build_curve_path(
                self.fn_curve, self.current_y, r, step, disp)
            self._path_keys["Q"] = (self.Q, self.K) + self._geom_key(r)
        return self._fam_paths, self._boundary_path

    def _ensure_current_path(self, r: QRectF) -> QPainterPath:
        """Layer B 路径：当前 Q 曲线（按 Q+K+几何 缓存，Q 变化时只重建它）。"""
        key = (self.Q, self.K) + self._geom_key(r)
        if self._path_keys["Q"] != key:
            step = self._render_step(len(self.fn_curve))
            disp = self._display_sample(r, step)
            self._cur_path = self._build_curve_path(
                self.fn_curve, self.current_y, r, step, disp)
            self._path_keys["Q"] = key
        return self._cur_path

    def workpoint_on_current_curve_px(self) -> float:
        """工作点中心与当前 Q 曲线在同一 fn 下的像素 Y 差（需求 1 验收）。

        用当前绘图区几何重建/复用已缓存当前曲线路径，读取工作点 fn 处的插值
        渲染像素 Y，与工作点增益的映射像素 Y 求差的绝对值。当工作点增益落在
        可视区 ``(0, ymax]`` 之外（曲线被裁剪、点被夹取到边缘）时无意义，
        返回 ``math.inf`` 由调用方自行跳过。仅重建像素路径，不重算任何数学数据。
        """
        r = self._plot_rect(self.width(), self.height())
        cur = self._ensure_current_path(r)
        mwork = float(llc_gain(self.fn_work, self.K, self.Q))
        if not (0.0 < mwork <= self.ymax):
            return math.inf
        x_fn = self._map_x(self.fn_work, r)
        y_path = _path_y_at(cur, x_fn)
        if y_path is None:
            return math.inf
        y_wp = self._map_y(mwork, r)
        return abs(y_path - y_wp)

    # ------------------------------------------------------------------
    # 基底（Layer A + B）渲染
    # ------------------------------------------------------------------
    def _y_ticks(self):
        """基于 ymax 的 nice ticks（步长取 1/2/2.5/5 × 10^n）。

        刻度从 0 递增到"首个 ≥ ymax 的步长整数倍"，保证顶部刻度即为规整值
        （如 ymax=2.2 → 0,0.5,...,2.5），绝不出现 2.2 这类非 nice 顶值。
        """
        ymax = max(0.01, float(self.ymax))
        target = 6.0
        raw = ymax / target
        if raw <= 0.0 or not math.isfinite(raw):
            return [0.0, ymax]
        exp = math.floor(math.log10(raw))
        base = 10.0 ** exp
        step = None
        for mult in _NICE_MULTS:
            cand = mult * base
            if cand <= 0.0:
                continue
            if (ymax / cand) <= 7.5:
                step = cand
                break
        if step is None:
            step = 10.0 * base
        if step <= 0.0:
            step = ymax / 6.0
        limit = math.ceil(ymax / step) * step  # 首个 ≥ ymax 的步长整数倍
        ticks = [round(v, 10) for v in
                 (limit * (i / max(1, int(round(limit / step))))
                  for i in range(int(round(limit / step)) + 1))]
        if not ticks or ticks[-1] < ymax:
            ticks.append(round(ymax, 10))
        return ticks

    def _minor_log_freqs(self):
        """log 横轴次网格：每个 decade 统一 2..9 × 10^n，再筛到当前范围。"""
        out = []
        for dec in range(-6, 7):  # 覆盖 1e-6..1e6，再筛
            e = dec
            for m in (2, 3, 4, 5, 6, 7, 8, 9):
                v = m * (10.0 ** e)
                if FN_MIN <= v <= FN_MAX:
                    out.append(v)
        return out

    def _x_major_ticks(self):
        """X 轴主刻度（需求 7.3）：0.1/0.2/0.5/1/2/5/10，筛到当前范围。

        主刻度画 tick mark + 数字 label；次刻度（0.3/0.4/.../9）只画较短 tick。
        """
        return [v for v in (0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0)
                if FN_MIN <= v <= FN_MAX]

    def _x_minor_ticks(self):
        """X 轴次刻度：0.3/0.4/0.6/0.7/0.8/0.9/3/4/6/7/8/9，筛到当前范围。"""
        return [v for v in (0.3, 0.4, 0.6, 0.7, 0.8, 0.9,
                            3.0, 4.0, 6.0, 7.0, 8.0, 9.0)
                if FN_MIN <= v <= FN_MAX]

    def _draw_scene_static(self, p: QPainter, r: QRectF) -> None:
        """Layer A：静息基底（背景/网格/坐标轴/图例 + 参考族 + 边界 + fnp/fnr 竖线）。

        此层缓存在 ``_base_pixmap``，只有 K / plot 尺寸 / ymax / theme 变化才重建。
        ``_ensure_backdrop`` 提供不随 K 变化的网格/坐标轴/刻度文字并优先合成，
        K 依赖内容（参考族/边界/谐振竖线）此处仅重绘。
        """
        bd = self._ensure_backdrop()
        if bd is not None:
            p.drawPixmap(0, 0, bd)
        # 网格已画入 backdrop；这里补画 K 依赖的内容
        fam, bnd = self._ensure_static_paths(r, self._preview)
        self._draw_family(p, r, fam)
        self._draw_boundary(p, r, bnd)
        self._draw_m_band(p, r)      # M 范围带（显示层）
        self._draw_fn_band(p, r)     # fn 范围带（显示层）
        self._draw_resonance_vlines(p, r)   # fnp/fnr 竖线（随 K 变化）
        # 图例独立成条带 pixmap（见 _ensure_legend_strip），不在此层以免 Q 文本失效

    def _draw_semi(self, p: QPainter, r: QRectF) -> None:
        """Layer B：当前 Q 曲线 + fnp/fnr/峰值 marker（只随 Q/K 重建）。"""
        cur = self._ensure_current_path(r)
        self._draw_current(p, r, cur)
        self._draw_semi_markers(p, r)

    def _draw_background(self, p: QPainter, r: QRectF) -> None:
        p.fillRect(r, QColor("white"))

    def _draw_family(self, p: QPainter, r: QRectF, fam) -> None:
        if not self.show_reference:      # 隐藏层不绘制（见需求七/二十八）
            return
        p.save()
        p.setClipRect(r)
        for path, col in zip(fam, FAMILY_COLORS):
            p.setPen(QPen(_hex(col), 1.2))
            if not path.isEmpty():
                p.drawPath(path)
        p.restore()

    def _draw_current(self, p: QPainter, r: QRectF, cur) -> None:
        p.save()
        p.setClipRect(r)
        p.setPen(QPen(_hex(CURRENT_COLOR), 2.6))
        if cur is not None and not cur.isEmpty():
            p.drawPath(cur)
        p.restore()

    def _draw_boundary(self, p: QPainter, r: QRectF, bnd) -> None:
        if not self.show_boundary:       # 隐藏层不绘制（见需求八/二十八）
            return
        p.save()
        pen = QPen(_hex(BOUNDARY_COLOR), 3.2)
        pen.setStyle(Qt.DashLine)
        pen.setDashPattern([10.0, 4.0])
        p.setPen(pen)
        p.setClipRect(r)
        if bnd is not None and not bnd.isEmpty():
            p.drawPath(bnd)
        # 竖直段（fn=1、M=1→0）：与弯曲段同一 pen，不新增图例条目（需求 3.2C）
        vp = self._boundary_vline_path
        if vp is not None and not vp.isEmpty():
            p.drawPath(vp)
        p.restore()
        # 线旁标注（跟随 K 自动调整，尽量避开峰值区）
        self._draw_boundary_label(p, r, bnd)

    def _draw_boundary_label(self, p: QPainter, r: QRectF, bnd) -> None:
        """在阻容分界线上方绘制 <阻容分界线> 小标签（名称不含 ∠Zin=0，需求 3.1）。"""
        fn_lab = 0.9
        if not (FN_MIN < fn_lab <= 1.0):
            return
        mb = boundary_gain(fn_lab, self.K)
        if mb is None or not math.isfinite(mb):
            return
        x = self._map_x(fn_lab, r)
        if x < r.left() or x > r.right():
            return
        y = self._map_y_full(mb, r)
        font = self._legend_font(float(self.height()))
        p.save()
        p.setFont(font)
        met = QFontMetrics(font)
        label = "阻容分界线"
        tw = met.horizontalAdvance(label)
        th = met.height()
        pad = 3
        box = QRectF(x - tw / 2 - pad, y - th - 8, tw + 2 * pad, th + 2 * pad)
        # 保持在图内
        if box.left() < r.left():
            box.moveLeft(r.left() + 2)
        if box.right() > r.right():
            box.moveRight(r.right() - 2)
        if box.top() < r.top():
            box.moveTop(r.top() + 2)
        p.setBrush(QColor(255, 255, 255, 235))
        p.setPen(QPen(_hex(BOUNDARY_LABEL_COLOR), 1.0))
        p.drawRect(box)
        p.setPen(_hex(BOUNDARY_LABEL_COLOR))
        p.drawText(box, Qt.AlignCenter, label)
        p.restore()

    def _draw_m_band(self, p: QPainter, r: QRectF) -> None:
        """M_req_min ~ M_req_max 水平范围带（淡色半透明，只显示不计算）。"""
        if not self.show_m_range:
            return
        a, b = float(self.m_req_min), float(self.m_req_max)
        if not (math.isfinite(a) and math.isfinite(b)):
            return
        lo, hi = min(a, b), max(a, b)
        y_lo = self._map_y_full(lo, r)
        y_hi = self._map_y_full(hi, r)
        band = QRectF(r.left(), y_hi, r.width(), y_lo - y_hi)
        if band.height() <= 0.0:
            return
        p.save()
        p.setClipRect(r)
        fill = QColor(M_BAND_COLOR)
        fill.setAlpha(24)
        p.fillRect(band, fill)
        pen = QPen(_hex(M_BAND_COLOR), 0)
        pen.setWidthF(0)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(band.left(), y_hi, band.right(), y_hi)
        p.drawLine(band.left(), y_lo, band.right(), y_lo)
        p.restore()

    def _draw_fn_band(self, p: QPainter, r: QRectF) -> None:
        """fn_min ~ fn_max 竖直范围带（淡色半透明，只显示不计算）。"""
        if not self.show_fn_range:
            return
        a, b = float(self.fn_min_band), float(self.fn_max_band)
        if not (math.isfinite(a) and math.isfinite(b)):
            return
        lo, hi = min(a, b), max(a, b)
        x_lo = self._map_x(lo, r)
        x_hi = self._map_x(hi, r)
        band = QRectF(x_lo, r.top(), x_hi - x_lo, r.height())
        if band.width() <= 0.0:
            return
        p.save()
        p.setClipRect(r)
        fill = QColor(FN_BAND_COLOR)
        fill.setAlpha(24)
        p.fillRect(band, fill)
        pen = QPen(_hex(FN_BAND_COLOR), 0)
        pen.setWidthF(0)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.drawLine(x_lo, band.top(), x_lo, band.bottom())
        p.drawLine(x_hi, band.top(), x_hi, band.bottom())
        p.restore()

    def _draw_grid(self, p: QPainter, r: QRectF) -> None:
        p.save()
        p.setClipRect(r)
        # 主网格（log 横轴各位 + Y nice 刻度）
        pen = QPen(QColor(0, 0, 0, 60))
        pen.setWidthF(0.7)
        p.setPen(pen)
        for dec in range(-6, 7):
            v = 10.0 ** dec
            if FN_MIN <= v <= FN_MAX:
                x = self._map_x(v, r)
                p.drawLine(x, r.top(), x, r.bottom())
        for v in self._y_ticks():
            y = self._map_y(v, r)
            p.drawLine(r.left(), y, r.right(), y)
        # 次网格（log 横轴 2..9 每 decade）—— 用可辨识的实线浅灰，避免与主网混淆但可见
        pen2 = QPen(QColor(0, 0, 0, 42))
        pen2.setWidthF(0.5)
        p.setPen(pen2)
        for v in self._minor_log_freqs():
            x = self._map_x(v, r)
            p.drawLine(x, r.top(), x, r.bottom())
        p.restore()

    def _draw_semi_markers(self, p: QPainter, r: QRectF) -> None:
        """fnp/fnr 标记与当前 Q 峰值点（Layer B，只随 Q/K 变化）。"""
        p.save()
        fnp = self.fnp
        fnr = self.fnr
        fn_peak, m_peak = self.peak

        def draw(xpx, ypx, shape: str, color: QColor):
            p.setPen(QPen(color, 2.0))
            p.setBrush(Qt.NoBrush)
            rad = 5.0
            if shape == "circle":
                p.drawEllipse(xpx - rad, ypx - rad, 2 * rad, 2 * rad)
            elif shape == "square":
                p.drawRect(xpx - rad, ypx - rad, 2 * rad, 2 * rad)
            elif shape == "diamond":
                p.drawPolygon(QPolygonF([
                    QPointF(xpx, ypx - rad), QPointF(xpx + rad, ypx),
                    QPointF(xpx, ypx + rad), QPointF(xpx - rad, ypx)]))
            elif shape == "triangle":
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(_hex(CURRENT_COLOR), 2.0))
                p.drawPolygon(QPolygonF([
                    QPointF(xpx, ypx - rad), QPointF(xpx + rad, ypx + rad),
                    QPointF(xpx - rad, ypx + rad)]))

        draw(self._map_x(fnp, r), self._map_y(float(llc_gain(fnp, self.K, self.Q)), r),
             "circle", _hex(FNP_COLOR))
        draw(self._map_x(fnr, r), self._map_y(float(llc_gain(fnr, self.K, self.Q)), r),
             "square", _hex(FNR_COLOR))
        if math.isfinite(fn_peak) and math.isfinite(m_peak):
            draw(self._map_x(fn_peak, r), self._map_y(m_peak, r),
                 "triangle", _hex(CURRENT_COLOR))
        p.restore()

    def _draw_axes(self, p: QPainter, r: QRectF) -> None:
        p.save()
        # 主次框线
        p.setPen(QPen(QColor(40, 40, 40), 1.0))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        p.drawLine(r.left(), r.top(), r.left(), r.bottom())
        # X 主刻度（需求 7.3）：0.1/0.2/0.5/1/2/5/10，画较长 tick mark
        p.setPen(QPen(QColor(40, 40, 40), 1.0))
        for v in self._x_major_ticks():
            x = self._map_x(v, r)
            p.drawLine(x, r.bottom(), x, r.bottom() + 6)
        # X 次刻度（0.3/0.4/.../9）：画较短 tick mark，不显示数字
        p.setPen(QPen(QColor(90, 90, 90), 0.8))
        for v in self._x_minor_ticks():
            x = self._map_x(v, r)
            p.drawLine(x, r.bottom(), x, r.bottom() + 3)
        # Y 主刻度（nice ticks）
        p.setPen(QPen(QColor(40, 40, 40), 1.0))
        for v in self._y_ticks():
            y = self._map_y(v, r)
            p.drawLine(r.left() - 5, y, r.left(), y)
        p.restore()

    def _draw_labels(self, p: QPainter, r: QRectF) -> None:
        p.save()
        font = self.font() or QFont()
        font.setPointSizeF(max(8.0, self.height() / 90.0))
        p.setFont(font)
        met = p.fontMetrics()
        # 横坐标 tick label（需求 7.4）：r.bottom()+3 ~ +19，与轴标题纵向分离
        for v in self._x_major_ticks():
            x = self._map_x(v, r)
            text = f"{v:g}"
            tw = met.horizontalAdvance(text)
            p.drawText(QRectF(x - tw / 2, r.bottom() + 3, tw, 16),
                       Qt.AlignHCenter, text)
        # 横轴标题（需求 7.4）：r.bottom()+24 ~ +46，位于刻度数字下方
        p.drawText(QRectF(r.left(), r.bottom() + 24, r.width(), 22),
                   Qt.AlignHCenter, "归一化频率 fn = fs / fr")
        # y 轴标签（旋转）
        p.save()
        p.translate(r.left() - 40, r.top() + r.height() / 2)
        p.rotate(-90)
        p.drawText(QRectF(-r.height() / 2, 0, r.height(), 22),
                   Qt.AlignHCenter, "增益 Mg")
        p.restore()
        # y 刻度文字（nice ticks）
        for v in self._y_ticks():
            y = self._map_y(v, r)
            text = self._fmt_ytick(v)
            tw = met.horizontalAdvance(text)
            p.drawText(QRectF(r.left() - 6 - tw, y - 8, tw, 16),
                       Qt.AlignRight | Qt.AlignVCenter, text)
        # 竖线标签
        p.setPen(_hex(FNP_COLOR))
        x = self._map_x(self.fnp, r)
        p.drawText(QRectF(x + 4, r.top() + 4, 90, 18), Qt.AlignLeft, "fnp")
        p.setPen(_hex(FNR_COLOR))
        x = self._map_x(self.fnr, r)
        p.drawText(QRectF(x + 4, r.top() + 22, 90, 18), Qt.AlignLeft, "fnr=1")
        p.setPen(_hex(WORK_COLOR))
        x = self._map_x(self.fn_work, r)
        p.drawText(QRectF(x + 4, r.bottom() - 22, 90, 18), Qt.AlignLeft, "当前 fn")
        p.restore()

    @staticmethod
    def _fmt_ytick(v: float) -> str:
        if abs(v - round(v)) < 1e-9:
            return f"{v:g}"
        # 保留足够位避免 0.5 / 0.25 显示失真
        s = f"{v:.6f}".rstrip("0").rstrip(".")
        return s

    def _legend_strip_geometry(self, w: float, h: float):
        """图例条带尺寸与布局（基于窗口宽度/高度，独立于绘图区）。"""
        avail = max(80.0, float(w) - 74.0 - 26.0)
        lay = self._legend_layout(avail, max(80.0, float(h)))
        entries = lay["entries"]
        cols, rows = lay["cols"], lay["rows"]
        row_h = lay["row_h"]
        pad_x, pad_y = 10, 4
        swatch = 16
        cell_w = [swatch + 6 + ww for ww in self._col_widths(entries, cols, rows, lay)]
        total_w = int(sum(cell_w) + (cols - 1) * 18 + 2 * pad_x)
        total_h = int(rows * row_h + pad_y)
        return lay, cell_w, total_w, total_h

    def _draw_legend_at(self, p: QPainter, lay, cell_w, total_w, total_h,
                        box_x: float, box_y: float) -> None:
        entries = lay["entries"]
        cols, rows = lay["cols"], lay["rows"]
        row_h = lay["row_h"]
        pad_x, pad_y = 10, 4
        swatch = 16
        for idx, (color, width, style, txt) in enumerate(entries):
            col = idx % cols
            row = idx // cols
            x = box_x + pad_x + sum(cell_w[:col]) + col * 18
            y = box_y + pad_y + row * row_h
            pen = QPen(_hex(color), width)
            pen.setStyle(style)
            p.setPen(pen)
            cx = x
            p.drawLine(cx, y + row_h / 2, cx + swatch, y + row_h / 2)
            p.setPen(QPen(QColor(20, 20, 20)))
            p.drawText(QRectF(cx + swatch + 6, y, cell_w[col], row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, txt)

    #: 图例条带 pixmap 缓存（随 Q/K/尺寸重建；fn 变化零重建）
    _legend_pixmap = None
    _legend_key = None

    def _ensure_legend_strip(self, w: int, h: int) -> QPixmap | None:
        """图例条带独立 pixmap：只在 Q/尺寸/布局变化时重建。

        图例文本只依赖 Q（"当前 Q 曲线"条目）与布局，不依赖 K；K 拖动时复用，
        避免每帧重建图例条带（需求 6）。
        """
        lay, cell_w, total_w, total_h = self._legend_strip_geometry(w, h)
        key = (int(w), int(h), round(self.Q, 6), lay["cols"])
        if self._legend_pixmap is not None and self._legend_key == key:
            return self._legend_pixmap
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(max(1, round(w * dpr))),
                     int(max(1, round(total_h * dpr))))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setBrush(QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
        p.drawRect(QRectF(74.0, 4.0, total_w, total_h))
        p.setFont(lay["font"])
        self._draw_legend_at(p, lay, cell_w, total_w, total_h, 74.0, 4.0)
        p.end()
        self._legend_pixmap = pm
        self._legend_key = key
        return pm

    def _draw_legend(self, p: QPainter, r: QRectF) -> None:
        """导出/离屏路径用的图例（画在绘图区正上方条带）。"""
        lay, cell_w, total_w, total_h = self._legend_strip_geometry(
            float(self.width()), float(self.height()))
        box_y = max(0.0, r.top() - total_h - 4)
        p.save()
        p.setFont(lay["font"])
        p.setBrush(QColor(255, 255, 255, 235))
        p.setPen(QPen(QColor(0, 0, 0, 90), 0.8))
        p.drawRect(QRectF(74.0, box_y, total_w, total_h))
        self._draw_legend_at(p, lay, cell_w, total_w, total_h, 74.0, box_y)
        p.restore()

    def _col_widths(self, entries, cols, rows, lay):
        """按列分配：每列宽 = 该列内最宽条目的文字宽度。"""
        widths = [0] * cols
        n = len(entries)
        txtw = lay["col_w"]
        for idx in range(n):
            col = idx % cols
            if txtw[idx] > widths[col]:
                widths[col] = txtw[idx]
        return widths

    def _draw_resonance_vlines(self, p: QPainter, r: QRectF) -> None:
        """fnp / fnr 竖线（随 K/Q 变化，放基底）。"""
        p.save()
        p.setClipRect(r)
        p.setPen(QPen(_hex(FNP_COLOR), 1.3, Qt.DashLine))
        x = self._map_x(self.fnp, r)
        p.drawLine(x, r.top(), x, r.bottom())
        p.setPen(QPen(_hex(FNR_COLOR), 1.3, Qt.DashLine))
        x = self._map_x(self.fnr, r)
        p.drawLine(x, r.top(), x, r.bottom())
        p.restore()

    def _draw_work_vline(self, p: QPainter, r: QRectF) -> None:
        """当前 fn 竖线（Overlay）。"""
        p.save()
        p.setPen(QPen(_hex(WORK_COLOR), 1.5, Qt.DotLine))
        x = self._map_x(self.fn_work, r)
        p.drawLine(x, r.top(), x, r.bottom())
        p.restore()

    def _draw_overlay(self, p: QPainter, r: QRectF) -> None:
        """Layer C：fn 竖线 + 工作点 + Hover 高亮与 Tooltip。"""
        self._draw_work_vline(p, r)
        # 工作点菱形
        mwork = float(llc_gain(self.fn_work, self.K, self.Q))
        xw = self._map_x(self.fn_work, r)
        yw = self._map_y(mwork, r)
        p.save()
        p.setPen(QPen(_hex(WORK_COLOR), 2.0))
        p.setBrush(Qt.NoBrush)
        rad = 5.0
        p.drawPolygon(QPolygonF([
            QPointF(xw, yw - rad), QPointF(xw + rad, yw),
            QPointF(xw, yw + rad), QPointF(xw - rad, yw)]))
        p.restore()
        if self._hover is not None:
            self._draw_hover(p, r)

    # ------------------------------------------------------------------
    # 基底 pixmap 缓存与 paintEvent
    # ------------------------------------------------------------------
    def _ensure_backdrop(self) -> QPixmap | None:
        """不随 K 变化的背景层（白底+网格+坐标轴+刻度文字），独立缓存。

        只按 widget 尺寸 / ymax / DPR / 字号 / **绘图区几何**重建。K/Q/fn 变化均
        完全复用，是 K 拖动"不重画网格与文字"的关键。

        注意：缓存键用绘图区 rect 几何（而非 ``_geom_gen``），这样图例可见性变化
        （改变 plot_rect 顶部偏移）会触发重建（BUG1），而纯 K 拖动不改变 plot_rect，
        背景层被复用，避免 K 拖动每帧重画网格/刻度文字（需求 6）。
        """
        w = int(self.width())
        h = int(self.height())
        if w <= 4 or h <= 4:
            return None
        dpr = self.devicePixelRatioF()
        scale = self.height()
        r = self._plot_rect(w, h)
        key = (w, h, round(self.ymax, 4), round(dpr, 4), int(scale),
               round(r.left(), 3), round(r.top(), 3),
               round(r.width(), 3), round(r.height(), 3))
        if (self._backdrop_pixmap is not None
                and self._backdrop_key == key):
            return self._backdrop_pixmap
        pm = QPixmap(int(round(w * dpr)), int(round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("white"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self._draw_background(p, r)
        self._draw_grid(p, r)
        self._draw_axes(p, r)
        self._draw_labels(p, r)
        p.end()
        self._backdrop_pixmap = pm
        self._backdrop_key = key
        return pm

    def _ensure_base(self) -> bool:
        """在需要时重建基底 pixmap。返回本次是否重建。"""
        w = int(self.width())
        h = int(self.height())
        if w <= 4 or h <= 4:
            return False
        dpr = self.devicePixelRatioF()
        key = (w, h)
        need = (self._base_pixmap is None
                or self._base_dirty
                or self._base_key_size != key
                or abs(self._base_key_dpr - dpr) > 1e-6)
        if not need:
            return False
        r = self._plot_rect(w, h)
        pm = QPixmap(int(round(w * dpr)), int(round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(QColor("white"))
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self._draw_scene_static(p, r)
        p.end()
        self._base_pixmap = pm
        self._base_dirty = False
        self._base_key_size = key
        self._base_key_dpr = dpr
        return True

    def _ensure_semi_pixmap(self, r: QRectF) -> QPixmap | None:
        """Layer B 缓存：当前 Q 曲线 + fnp/fnr/峰值 marker 合成图。

        只随 Q / K / plot 尺寸变化重建。fn 拖动零重建，paintEvent 直接 blit。
        """
        w = int(self.width())
        h = int(self.height())
        if w <= 4 or h <= 4:
            return None
        key = self._geom_key(r) + (round(self.Q, 6), round(self.K, 6))
        if self._semi_pixmap is not None and self._semi_key == key:
            return self._semi_pixmap
        dpr = self.devicePixelRatioF()
        pm = QPixmap(int(round(w * dpr)), int(round(h * dpr)))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        self._draw_semi(p, r)
        p.end()
        self._semi_pixmap = pm
        self._semi_key = key
        return pm

    def paintEvent(self, event) -> None:  # noqa: N802
        _t0 = self._time.perf_counter() if self._collect_perf else None
        self._ensure_base()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        if self._base_pixmap is not None:
            painter.drawPixmap(0, 0, self._base_pixmap)
            lg = self._ensure_legend_strip(self.width(), self.height())
            if lg is not None:
                painter.drawPixmap(0, 0, lg)   # 顶部图例条带
            r = self._plot_rect(self.width(), self.height())
            semi = self._ensure_semi_pixmap(r)   # Layer B（Q/K 缓存）
            if semi is not None:
                painter.drawPixmap(0, 0, semi)
            self._draw_overlay(painter, r)       # Layer C：fn/工作点/Hover
        painter.end()
        if _t0 is not None:
            self._paint_ms.append((self._time.perf_counter() - _t0) * 1000.0)

    # ------------------------------------------------------------------
    # Hover Inspector
    # ------------------------------------------------------------------
    def _clear_hover_state(self):
        self._hover = None
        self._hover_rect = None
        self._hover_mouse = None

    def _boundary_visible_domain(self):
        """阻容分界线弯曲段的可见 fn 域：``boundary_x[0] ~ boundary_x[-1]``。

        真正画出的弯曲段从 fnp 到 fn=1（见 ``_compute_boundary``）；fn>1 区域图上
        没有边界线，Hover 绝不能对数学外推的隐藏曲线构造候选（需求 6）。
        """
        if not self.boundary_x:
            return None
        return self.boundary_x[0], self.boundary_x[-1]

    def _candidates(self, fn_mouse):
        """返回候选曲线列表（每条含 kind / q / 颜色 / 曲线值函数）。

        隐藏层一律不进入候选：关闭参考 Q 曲线族 / 阻容分界线后，Hover 不再命中
        这些已隐藏曲线（与绘图、图例同一 visibility state，见需求二十八）。
        阻容分界线弯曲段只在**实际画出的 fn 域**（fnp ~ fn=1）内才进入候选，
        fn>1 的"数学外推隐藏曲线"绝不参与 Hover（需求 6.1A）。
        """
        out = []
        if self.show_reference:
            for q, col in zip(Q_FAMILY, FAMILY_COLORS):
                out.append({"kind": "family", "q": float(q), "color": col})
        out.append({"kind": "current", "q": float(self.Q),
                    "color": CURRENT_COLOR})
        if self.show_boundary:
            dom = self._boundary_visible_domain()
            if dom is not None and dom[0] <= fn_mouse <= dom[1]:
                out.append({"kind": "boundary", "q": None, "color": BOUNDARY_COLOR})
        return out

    def _curve_m_at(self, kind, q, fn_mouse):
        """某候选曲线在 fn_mouse 处的精确增益（标量，仅 1 个点）。

        阻容分界线弯曲段只在可见域内求值；fn 超出 ``boundary_x`` 范围时返回
        None（双保险，需求 6.1B），绝不外推出一条隐藏曲线。
        """
        if kind == "boundary":
            dom = self._boundary_visible_domain()
            if dom is None or not (dom[0] <= fn_mouse <= dom[1]):
                return None
            m = boundary_gain(fn_mouse, self.K)
            return m
        return float(llc_gain(fn_mouse, self.K, q))

    def _vertical_boundary_hit(self, screen_x: float, screen_y: float,
                               r: QRectF, tol: float):
        """阻容分界线竖直段（fn=1、M=1→0）的独立几何 hit test（需求 3.4）。

        竖直段不是单值函数 M(fn)，不能用 ``boundary_gain`` 表示；这里直接判断
        鼠标到 x(fn=1) 的像素距离，且 mouse_y 必须落在 M=0~1 对应像素范围内。
        命中时反算 M（鼠标 y 对应值，∈[0,1]），绝不伪造 ``boundary_gain(1)``。
        """
        if not self.show_boundary:
            return None
        x1 = self._map_x(1.0, r)
        y_top = self._map_y_full(1.0, r)   # M=1 的像素 y
        y_bot = self._map_y_full(0.0, r)   # M=0 的像素 y（= 绘图区底边）
        if not (y_top - tol <= screen_y <= y_bot + tol):
            return None
        if abs(screen_x - x1) > tol:
            return None
        span = (y_bot - y_top) or 1.0
        m_est = max(0.0, min(1.0, (y_bot - screen_y) / span))
        return {
            "kind": "boundary", "q": None, "color": BOUNDARY_COLOR,
            "fn": 1.0, "m": m_est,
            "screen_x": x1, "screen_y": screen_y,
            "dist": abs(screen_x - x1), "priority": _HOVER_PRIORITY["boundary"],
            "qb": None, "mb": m_est,
        }

    def hit_test(self, screen_x: float, screen_y: float, plot_rect: QRectF = None):
        """命中检测：纯数学 + 像素距离，O(候选数) 复杂度。

        返回 hit dict 或 None（超过容差）。``plot_rect`` 缺省用当前尺寸。
        """
        r = plot_rect or self._plot_rect(float(self.width()), float(self.height()))
        if r.width() <= 0.0 or r.height() <= 0.0:
            return None
        fn_mouse = self.pixel_to_fn(screen_x, r)
        if not (FN_MIN <= fn_mouse <= FN_MAX) or math.isnan(fn_mouse):
            return None
        tol = HOVER_TOL_PX
        best = None
        for cand in self._candidates(fn_mouse):
            kind = cand["kind"]
            m = self._curve_m_at(kind, cand["q"], fn_mouse)
            if m is None or math.isnan(m):
                continue
            py = self._map_y_full(m, r)
            # 只考虑在图内 ± 容差范围的候选（避免远处误判/溢出像素）
            if py < r.top() - tol or py > r.bottom() + tol:
                continue
            if screen_y is None:
                return None
            dist = abs(py - screen_y)
            if dist > tol:
                continue
            prio = _HOVER_PRIORITY[kind]
            if best is None or dist < best["dist"] - 1e-9 or (
                    abs(dist - best["dist"]) <= 1e-9 and prio < best["priority"]):
                best = {
                    "kind": kind, "q": cand["q"], "color": cand["color"],
                    "fn": fn_mouse, "m": m,
                    "screen_x": self._map_x(fn_mouse, r), "screen_y": py,
                    "dist": dist, "priority": prio,
                    "qb": None, "mb": None,
                }
        # 竖直边界段候选（fn=1、M=1→0，需求 3.4）：与弯曲段/曲线候选统一比距离
        vhit = self._vertical_boundary_hit(screen_x, screen_y, r, tol)
        if vhit is not None:
            if best is None or vhit["dist"] < best["dist"] - 1e-9 or (
                    abs(vhit["dist"] - best["dist"]) <= 1e-9
                    and vhit["priority"] < best["priority"]):
                best = vhit
        if best is None:
            return None
        # 补充边界量 / 区域
        best["region"] = input_region(fn_mouse, self.K, self.Q)
        if best["kind"] == "boundary":
            if best.get("mb") is None:
                # 弯曲段：按 fn_mouse 精确计算；竖直段已自带反算 mb，不覆盖
                best["mb"] = boundary_gain(fn_mouse, self.K)
                best["qb"] = q_boundary_for_fn(fn_mouse, self.K)
        return best

    def _tooltip_lines(self, hit) -> list:
        """Hover 信息行：返回 ``(style, text)`` 列表。

        style ∈ {"header", "bold", "normal", "region"}: 驱动颜色/字重层级。
        """
        if hit["kind"] == "boundary":
            lines = [
                ("header", "阻容分界线"),
                ("normal", "∠Zin = 0"),
                ("normal", f"K = {self.K:.3f}"),
                ("bold", f"fn = {hit['fn']:.4f}"),
                ("normal", f"Mb = {_fmt_bound_val(hit['mb'])}"),
                ("normal", f"Qb = {_fmt_bound_val(hit['qb'])}"),
            ]
        else:
            lines = [
                ("header", "当前曲线"),
                ("normal", f"Q = {hit['q']:.4f}"),
                ("normal", f"K = {self.K:.3f}"),
                ("bold", f"fn = {hit['fn']:.4f}"),
                ("bold", f"M = {hit['m']:.4f}"),
            ]
        lines.append(
            ("normal", f"fs = {_fmt_freq(hit['fn'] * self.fr_khz * 1000.0)}"))
        rlabel = _REGION_LABEL.get(hit["region"], hit["region"])
        style = "region_inductive" if hit["region"] == "inductive" \
            else "region_capacitive"
        lines.append((style, f"区域：{rlabel}"))
        return lines

    def _tooltip_geometry(self, mouse_pos, n_lines, widget_w, widget_h):
        """Tooltip 位置：四象限自适应，避免盖住鼠标点。

        优先右上；右边界不足翻到左；上边界不足翻到下；两向都受限时
        让 tooltip 尽量贴合交点而不遮蔽命中点。
        """
        font = self._legend_font(float(widget_h))
        met = QFontMetrics(font)
        pad_x, pad_y = 10, 8
        line_h = met.height() + 3
        w = 186 + 2 * pad_x
        h = n_lines * line_h + 2 * pad_y + 6
        mx, my = mouse_pos.x(), mouse_pos.y()
        # 优先右上（位于命中点右上方）
        if mx + 14 + w <= widget_w - 2 and my - 14 - h >= 2:
            x, y = mx + 14, my - 14 - h
        elif mx - 14 - w >= 2 and my - 14 - h >= 2:
            x, y = mx - 14 - w, my - 14 - h
        elif mx + 14 + w <= widget_w - 2 and my + 12 + h <= widget_h - 2:
            x, y = mx + 14, my + 12
        else:
            x, y = mx - 14 - w, my + 12
        x = max(2, min(x, int(widget_w) - 2 - w))
        y = max(2, min(y, int(widget_h) - 2 - h))
        return QRect(int(x), int(y), int(w), int(h))

    def _draw_hover(self, p: QPainter, r: QRectF) -> None:
        hit = self._hover
        if hit is None or self._hover_mouse is None:
            return
        # 高亮圆点
        rad = 5.0
        px, py = hit["screen_x"], hit["screen_y"]
        p.save()
        p.setPen(QPen(QColor("white"), 2.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QRectF(px - rad - 1.2, py - rad - 1.2,
                             2 * (rad + 1.2), 2 * (rad + 1.2)))
        p.setPen(QPen(_hex(hit["color"]), 2.2))
        p.drawEllipse(QRectF(px - rad, py - rad, 2 * rad, 2 * rad))
        p.restore()

        # Tooltip 工程信息卡（高对比，需求 4）
        lines = self._tooltip_lines(hit)
        base_font = self._legend_font(float(self.height()))
        tg = self._tooltip_geometry(
            self._hover_mouse, len(lines) + 1, float(self.width()),
            float(self.height()))
        p.save()
        met = QFontMetrics(base_font)
        line_h = met.height() + 3
        pad_x, pad_y = 10, 8
        # 阴影（右下轻偏移，低透明黑）
        sh = QPainterPath()
        sh.addRoundedRect(QRectF(tg).translated(3, 3), 6, 6)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 30))
        p.drawPath(sh)
        # 卡片底 + 边框（圆角 6）
        card = QPainterPath()
        card.addRoundedRect(QRectF(tg), 6, 6)
        p.setPen(QPen(HP_CARD_LINE, 1.0))
        p.setBrush(HP_CARD_BG)
        p.drawPath(card)
        # 文本（按 style 驱动颜色/字重）
        ty = tg.top() + pad_y
        for style, text in lines:
            f = QFont(base_font)
            if style == "header":
                pen = _hex("#2563EB")
                f.setBold(True)
            elif style == "bold":
                pen = HP_BOLD
                f.setBold(True)
            elif style in ("region_inductive", "region_capacitive"):
                pen = HP_BADGE_IN if style == "region_inductive" else HP_BADGE_CAP
            else:
                pen = HP_TEXT
            p.setFont(f)
            p.setPen(pen)
            p.drawText(QRectF(tg.left() + pad_x, ty, tg.width() - 2 * pad_x, line_h),
                       Qt.AlignLeft | Qt.AlignVCenter, text)
            ty += line_h
        p.restore()
        # 记录当前 rect 供局部刷新
        self._hover_rect = tg

    def _hover_dirty_rect(self) -> QRect | None:
        """合并旧/新 hover 高亮与 tooltip 的脏矩形（用于局部 update）。"""
        rects = []
        if self._hover_mouse is not None and self._hover is not None:
            rad = 8
            hx, hy = self._hover["screen_x"], self._hover["screen_y"]
            rects.append(QRect(int(hx - rad), int(hy - rad), 2 * rad, 2 * rad))
        if self._hover_rect is not None:
            rects.append(self._hover_rect)
        if not rects:
            return None
        union = QRect(rects[0])
        for rt in rects[1:]:
            union = union.united(rt)
        return union.adjusted(-4, -4, 4, 4)

    def _update_hover(self, pos) -> None:
        old_rect = self._hover_dirty_rect()
        old_hover = self._hover
        _t0 = self._time.perf_counter() if self._collect_perf else None
        hit = self.hit_test(pos.x(), pos.y())
        if _t0 is not None:
            self._hover_ms.append((self._time.perf_counter() - _t0) * 1000.0)
        self._hover = hit
        self._hover_mouse = pos
        new_rect = self._hover_dirty_rect()
        union = old_rect
        if new_rect is not None:
            union = union.united(new_rect) if union else new_rect
        if union is not None:
            self.update(union)
        elif old_hover is not None or hit is not None:
            self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        self._update_hover(event.position())
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        if self._hover is not None:
            self._clear_hover_state()
            self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        self._base_key_size = (-1, -1)
        self._base_dirty = True
        self._invalidate_geometry()
        self._clear_hover_state()
        super().resizeEvent(event)

    # ------------------------------------------------------------------
    # 导出 PNG（QPixmap/QImage/QPainter）
    # ------------------------------------------------------------------
    def _draw_scene(self, p: QPainter, r: QRectF, on_base: bool = True) -> None:
        """导出用完整场景（任意尺寸）：backdrop + 参考族 + 边界 + 谐振竖线 +
        Layer B（当前曲线/标记）+ 图例。``on_base`` 仅用于与旧签名兼容。
        """
        self._draw_background(p, r)
        self._draw_grid(p, r)
        self._draw_axes(p, r)
        self._draw_labels(p, r)
        fam, bnd = self._ensure_static_paths(r, preview=False)  # 导出恒全精度
        self._draw_family(p, r, fam)
        self._draw_boundary(p, r, bnd)
        self._draw_resonance_vlines(p, r)
        self._draw_semi(p, r)
        self._draw_legend(p, r)

    def render_to_png(self, path: str, size: QSize = QSize(1440, 900)) -> str:
        self._clear_hover_state()
        image = QImage(size, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor("white"))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(0.0, 0.0, size.width(), size.height())
        # PNG 用独立尺寸场景直接渲染（不用当前 widget 缓存，因尺寸不同）
        self._draw_scene(painter, self._plot_rect(size.width(), size.height()),
                         on_base=False)
        self._draw_overlay(painter, self._plot_rect(size.width(), size.height()))
        painter.end()
        if not os.path.isabs(path):
            path = os.path.abspath(path)
        ok = image.save(path, "PNG")
        if not ok:  # pragma: no cover
            raise OSError(f"保存 PNG 失败：{path}")
        return path

    @staticmethod
    def _hist(samples) -> dict:
        if not samples:
            return {"n": 0, "p50": float("nan"), "p95": float("nan"),
                    "max": float("nan")}
        s = sorted(samples)
        n = len(s)
        def pct(p):
            i = min(n - 1, int(p * n))
            return s[i]
        return {"n": n, "p50": round(pct(0.5), 4), "p95": round(pct(0.95), 4),
                "max": round(pct(1.0), 4)}

    def perf_stats(self) -> dict:
        """paint / hover 耗时分位数（P50/P95/max，ms）。"""
        return {"paint": self._hist(self._paint_ms),
                "hover": self._hist(self._hover_ms)}

    # 兼容 llc_plot 读取接口（供测试/导出）
    def artist_census(self) -> dict:
        return {
            "lines": 1 + len(Q_FAMILY),      # 当前 + 族（QPainter 无持久对象）
            "texts": 0,
            "collections": 0,
            "patches": 0,
            "legends": 1,
            "data_lists": sum(1 for y in self.family_y) + 2,
            "cache_paths": 3,
            "cache_base": 1,
        }