# -*- coding: utf-8 -*-
"""LLC 谐振变换器交互式多增益曲线 —— PySide6 桌面版。

由 MATLAB 程序 ``LLC_gain_interactive_multi_v2`` 移植而来。
数学模型见 :mod:`llc_model`，字体处理见 :mod:`cjk_font`，绘图层见 :mod:`llc_plot`。

符号体系（唯一、统一，与 MATLAB 原版相反并已彻底迁移）
------------------------------------------------------
    K  = Lm / Lr       励磁电感比（线性滑块，1.5 ~ 10，默认 5）
    Q  = sqrt(Lr/Cr)/Rac   品质因数（对数滑块，0.05 ~ 10，默认 0.5）
    fn = fs / fr       归一化开关频率（对数滑块，0.1 ~ 10，默认 1）
    fr = 串联谐振频率（kHz，默认 124.4）

交互性能设计
------------
* **增量更新**：只按参数依赖关系重算必要部分（详见 :mod:`llc_plot.GainPlot.refresh`）。
  K 改变才重算固定参考 Q 曲线族；Q 改变只重算当前黑色曲线；fn 改变只移动工作点；
  fr/纵轴上限改变轻量更新。
* **QTimer 合并高频滑块事件**：滑块 `valueChanged` 只记录"最新目标参数"并置
  dirty flag，再由一个单次 QTimer（默认 16 ms，约 60 FPS）合并触发刷新；
  若上一次刷新尚未结束，新事件只覆盖 pending 值而不排队执行历史值。
* **滑块释放立即高精度刷新**：连接 `sliderReleased`，松手瞬间做一次全量最终刷新，
  确保界面精确落在最终值，不受拖动期间预览精度影响。

标题布局修复
------------
顶部为独立的 Qt 标题/状态行（固定标题 + 动态参数），不使用会随 DPI/窗口缩放
被 Matplotlib 上边距裁切的超长坐标轴 title。
"""

from __future__ import annotations

import math
import os
import sys

# 同步导入顺序：PlotWidget / 数学层均为纯 Python（无 numpy / matplotlib），
# 显著降低冷启动与最终体积。
from PySide6.QtCore import QObject, Qt, QTimer, QElapsedTimer  # noqa: E402
from PySide6.QtGui import QFont  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

# 兼容两种运行方式：直接运行 src/main.py，以及 PyInstaller 打包后运行
if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cjk_font import qt_font_family  # noqa: E402
from plot_widget import GainPlotWidget  # noqa: E402
from llc_py import (  # noqa: E402
    DEFAULT_FN,
    DEFAULT_FR_KHZ,
    DEFAULT_K,
    DEFAULT_Q,
    DEFAULT_YMAX,
    FN_MAX,
    FN_MIN,
    K_MAX,
    K_MIN,
    Q_MAX,
    Q_MIN,
    format_result_text,
)

APP_TITLE = "LLC 谐振变换器交互式多增益曲线"

# 滑块使用整数刻度模拟连续/对数取值
SLIDER_STEPS = 1000

#: 拖动期间刷新合并间隔（毫秒）。16 ms ≈ 60 FPS；33 ms ≈ 30 FPS。
REFRESH_MS = 16

#: 环境变量或命令行开关：开启性能日志（默认关闭）
PERF_LOG_ENV = "LLC_PERF_LOG"

#: 启动性能测量：设 LLC_TIMING=1 后，记录 T0..T5 时间戳并自动退出。
#: 仅在 LLC_TIMING 下启用；正常启动零开销（不写文件/不建 timer/不产生 UI）。
TIMING_ENV = "LLC_TIMING"
_TIMING_ENABLED: bool = os.environ.get(TIMING_ENV, "") in ("1", "true", "on")
_TIMING_FILE: str = os.environ.get(
    "LLC_TIMING_FILE", "llc_timing.json"
).strip()
_TIMING: dict[str, float] = {}
_TIMING_START: float = 0.0


def _timing_mark(name: str) -> None:
    """记录一次命名时间戳（相对进程首次调用 _timing_start 的时刻，秒）。"""
    global _TIMING_START
    if _TIMING_START <= 0.0:
        import time as _t

        _TIMING_START = _t.perf_counter()
    import time as _t

    _TIMING[name] = _t.perf_counter() - _TIMING_START


def _timing_finish() -> None:
    """定时模式收尾：写入 JSON 后从事件循环退出，供外部脚本解析。"""
    app = QApplication.instance()
    _timing_mark("t5_cleanup")
    try:
        import json

        with open(_TIMING_FILE, "w", encoding="utf-8") as fh:
            json.dump(_TIMING, fh, indent=2)
    except OSError:
        pass
    if app is not None:
        app.exit(0)


class _ReadyMarker(QObject):
    """等待首个真实 paint 事件落地，再让事件循环兜一圈，才算"可交互"。

    只有 LLC_TIMING=1 时才会安装此事件过滤器，正常启动完全不参与。
    """

    def __init__(self, app, settle_ms: int = 120):
        super().__init__(app)
        self._app = app
        self._settle_ms = settle_ms
        self._painted = False

    def install(self, widget) -> None:
        widget.installEventFilter(self)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent

        if event.type() == QEvent.Paint and not self._painted:
            self._painted = True
            _timing_mark("t4_first_paint")
            # 首帧已提交：再让事件循环兜一次，确保能响应输入/重绘
            QTimer.singleShot(0, self._on_settle)
        return False

    def _on_settle(self) -> None:
        _timing_mark("t5_event_loop_ready")
        self._app.removeEventFilter(self)
        QTimer.singleShot(self._settle_ms, _timing_finish)


def _perf_log_enabled() -> bool:
    return os.environ.get(PERF_LOG_ENV, "") in ("1", "true", "on") \
        or "--perf" in sys.argv


def _lin_from_slider(value: int, lo: float, hi: float) -> float:
    """整数滑块 -> 线性实数。"""
    return lo + (hi - lo) * (value / SLIDER_STEPS)


def _slider_from_lin(value: float, lo: float, hi: float) -> int:
    return int(round((value - lo) / (hi - lo) * SLIDER_STEPS))


def _log_from_slider(value: int, lo: float, hi: float) -> float:
    """整数滑块 -> 对数实数（lo/hi 为实际值，非对数）。"""
    lg = math.log10(lo) + (math.log10(hi) - math.log10(lo)) * (value / SLIDER_STEPS)
    return float(10.0 ** lg)


def _slider_from_log(value: float, lo: float, hi: float) -> int:
    frac = (math.log10(value) - math.log10(lo)) / (math.log10(hi) - math.log10(lo))
    return int(round(frac * SLIDER_STEPS))


class MainWindow(QMainWindow):
    """主窗口：顶部标题/状态栏 + 左侧 QPainter 增益画布 + 右侧结果框 + 底部参数面板。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1420, 860)
        self.setMinimumSize(1040, 700)

        # ---- 状态 ----
        self._updating = False          # 回调重入锁
        self._pending = False

        # dirty 标志：记录哪些参数需要重新计算
        # 注意：dirty_k 表示 "K = Lm/Lr"（电感比）改变，会重算全部曲线；
        #       dirty_fn 表示 "fn = fs/fr"（工作点）改变，只移动工作点。
        self.dirty_k = False
        self.dirty_q = False
        self.dirty_fn = False
        self.dirty_fr = False
        self.dirty_ylim = False

        # 上次应用的参数（用于判断是否需要更新结果文本）
        self._last_applied = None

        # ---- 合并高频事件的单次 QTimer ----
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(REFRESH_MS)
        self._refresh_timer.timeout.connect(self._do_update)

        self._perf_log = _perf_log_enabled()
        self._perf = None
        if self._perf_log:
            self._perf = {
                "k_sum": 0.0, "k_n": 0,
                "q_sum": 0.0, "q_n": 0,
                "fn_sum": 0.0, "fn_n": 0,
                "draw_sum": 0.0, "frames": 0,
            }
            self._elapsed = QElapsedTimer()
            self._elapsed.start()

        self._build_ui()
        # 绘图控件：全图形对象由其内部只创建一次，增量刷新不增长
        self.plot = self.canvas
        self.ax = self.canvas

        # 初始全量刷新（refresh 会更新标题、曲线、结果）
        self._mark_all_dirty()
        self._do_update()

    # ------------------------------------------------------------------
    # 界面构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ---------- 顶部标题 / 状态栏（独立于 matplotlib，避免被裁切） ----------
        header = QHBoxLayout()
        header.setSpacing(10)
        self.titleLabel = QLabel("LLC 多增益曲线")
        title_font = QFont(qt_font_family() or "", 13, QFont.Bold)
        self.titleLabel.setFont(title_font)
        self.titleLabel.setMinimumHeight(28)
        header.addWidget(self.titleLabel)

        self.statusLabel = QLabel("")
        self.statusLabel.setFont(QFont(qt_font_family() or "", 11))
        self.statusLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.statusLabel.setMinimumHeight(28)
        header.addWidget(self.statusLabel, stretch=1)
        root.addLayout(header)

        # ---------- 上半部分：画布 + 结果框 ----------
        upper = QHBoxLayout()
        upper.setSpacing(8)

        self.canvas = GainPlotWidget()
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.setMinimumWidth(560)
        self.canvas.setMinimumHeight(420)
        upper.addWidget(self.canvas, stretch=3)

        self.resultBox = QPlainTextEdit()
        self.resultBox.setReadOnly(True)
        self.resultBox.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.resultBox.setMinimumWidth(330)
        self.resultBox.setMaximumWidth(430)
        self.resultBox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        mono = QFont(qt_font_family() or "Consolas", 10)
        self.resultBox.setFont(mono)
        upper.addWidget(self.resultBox, stretch=1)

        root.addLayout(upper, stretch=1)

        # ---------- 下半部分：参数调节 ----------
        panel = QGroupBox("参数调节")
        panel.setFont(QFont(qt_font_family() or "", 10, QFont.Bold))
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 14, 12, 10)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)

        # --- K = Lm/Lr（线性滑块，1.5~10，默认 5） ---
        grid.addWidget(QLabel("K = Lm/Lr"), 0, 0)
        self.sliderK = QSlider(Qt.Horizontal)
        self.sliderK.setRange(0, SLIDER_STEPS)
        self.sliderK.setValue(_slider_from_lin(DEFAULT_K, K_MIN, K_MAX))
        self.sliderK.setMinimumWidth(240)
        grid.addWidget(self.sliderK, 0, 1)
        self.labelK = QLabel("5.000")
        self.labelK.setMinimumWidth(66)
        grid.addWidget(self.labelK, 0, 2)
        grid.addWidget(QLabel(f"（范围 {K_MIN} ~ {K_MAX}）"), 0, 3)

        # --- Q（对数滑块） ---
        grid.addWidget(QLabel("当前 Q"), 1, 0)
        self.sliderQ = QSlider(Qt.Horizontal)
        self.sliderQ.setRange(0, SLIDER_STEPS)
        self.sliderQ.setValue(_slider_from_log(DEFAULT_Q, Q_MIN, Q_MAX))
        self.sliderQ.setMinimumWidth(240)
        grid.addWidget(self.sliderQ, 1, 1)
        self.labelQ = QLabel("0.5000")
        self.labelQ.setMinimumWidth(66)
        grid.addWidget(self.labelQ, 1, 2)
        grid.addWidget(QLabel(f"（对数，{Q_MIN} ~ {Q_MAX}）"), 1, 3)

        # --- fn = fs/fr（对数滑块，0.1~10，默认 1） ---
        grid.addWidget(QLabel("工作点 fn = fs/fr"), 0, 4)
        self.sliderFn = QSlider(Qt.Horizontal)
        self.sliderFn.setRange(0, SLIDER_STEPS)
        self.sliderFn.setValue(_slider_from_log(DEFAULT_FN, FN_MIN, FN_MAX))
        self.sliderFn.setMinimumWidth(240)
        grid.addWidget(self.sliderFn, 0, 5)
        self.labelFn = QLabel("1.0000")
        self.labelFn.setMinimumWidth(66)
        grid.addWidget(self.labelFn, 0, 6)
        grid.addWidget(QLabel(f"（对数，{FN_MIN} ~ {FN_MAX}）"), 0, 7)

        # --- fr / 纵轴上限 ---
        grid.addWidget(QLabel("fr / kHz"), 1, 4)
        fr_box = QHBoxLayout()
        self.editFr = QDoubleSpinBox()
        self.editFr.setDecimals(3)
        self.editFr.setRange(0.001, 1.0e7)
        self.editFr.setValue(DEFAULT_FR_KHZ)
        self.editFr.setSingleStep(1.0)
        self.editFr.setKeyboardTracking(False)
        self.editFr.setMinimumWidth(110)
        fr_box.addWidget(self.editFr)
        fr_box.addSpacing(14)
        fr_box.addWidget(QLabel("纵轴上限"))
        self.editYmax = QDoubleSpinBox()
        self.editYmax.setDecimals(2)
        self.editYmax.setRange(0.2, 100.0)
        self.editYmax.setValue(DEFAULT_YMAX)
        self.editYmax.setSingleStep(0.1)
        self.editYmax.setKeyboardTracking(False)
        self.editYmax.setMinimumWidth(100)
        fr_box.addWidget(self.editYmax)
        fr_box.addStretch(1)
        grid.addLayout(fr_box, 1, 5, 1, 3)

        self.hintLabel = QLabel(
            "参考曲线：Q = 0.1、0.2、0.5、0.8、1、2、5、8、10"
        )
        grid.addWidget(self.hintLabel, 2, 0, 1, 8)

        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(5, 3)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(7, 1)

        panel.setMaximumHeight(170)
        root.addWidget(panel, stretch=0)

        # ---------- 信号 ----------
        # valueChanged 只记录最新目标参数 + 置 dirty，不直接刷新
        self.sliderK.valueChanged.connect(self._on_k_changed)
        self.sliderQ.valueChanged.connect(self._on_q_changed)
        self.sliderFn.valueChanged.connect(self._on_fn_changed)
        self.editFr.valueChanged.connect(self._on_fr_changed)
        self.editYmax.valueChanged.connect(self._on_ymax_changed)

        # 松手时立即做一次全量高精度刷新
        self.sliderK.sliderReleased.connect(self._on_released)
        self.sliderQ.sliderReleased.connect(self._on_released)
        self.sliderFn.sliderReleased.connect(self._on_released)

    # ------------------------------------------------------------------
    # 参数变化回调：只标记，排队由 QTimer 合并
    # ------------------------------------------------------------------
    def _on_k_changed(self, *_):
        self.dirty_k = True
        self._schedule_refresh()

    def _on_q_changed(self, *_):
        self.dirty_q = True
        self._schedule_refresh()

    def _on_fn_changed(self, *_):
        self.dirty_fn = True
        self._schedule_refresh()

    def _on_fr_changed(self, *_):
        self.dirty_fr = True
        self._schedule_refresh()

    def _on_ymax_changed(self, *_):
        self.dirty_ylim = True
        self._schedule_refresh()

    def _on_released(self, *_):
        """滑块释放：只冲刷尚未 flush 的最后一个值，不做全量 dirty 重算。

        拖动期间 valueChanged 已把最新目标参数写入各自 dirty flag；若最后一个
        valueChanged 还未被合并计时器 flush，这里补一次；若已 flush，则各 dirty
        均为 False，执行一次极轻量的纯文本/元数据刷新即可。绝不在这里全量重算
        曲线族，避免"松手顿一下"。
        """
        if self._perf_log and self._perf:
            self._dump_perf()
        self._refresh_timer.stop()
        self._do_update()

    def _mark_all_dirty(self):
        self.dirty_k = True
        self.dirty_q = True
        self.dirty_fn = True
        self.dirty_fr = True
        self.dirty_ylim = True

    def _schedule_refresh(self):
        """启动合并计时器；若刷新正在进行或计时器已启动则不再重复启动。"""
        if self._updating:
            # 刷新进行中：记录 pending，完成后再补一次
            self._pending = True
            return
        if not self._refresh_timer.isActive():
            self._refresh_timer.start()

    # ------------------------------------------------------------------
    # 由 QTimer 触发的刷新入口（与 _do_update 同逻辑）
    # ------------------------------------------------------------------
    def _flush_refresh(self):
        self._do_update()

    def _do_update(self):
        """同步执行一次刷新（也用于滑块释放、初始和测试）。"""
        if self._updating:
            self._pending = True
            return
        self._updating = True
        try:
            self._apply_update()
        except Exception as exc:
            self._show_error(exc)
        finally:
            self._updating = False
            if self._pending:
                self._pending = False
                self._schedule_refresh()

    def _show_error(self, exc: Exception) -> None:
        """把异常显示在结果框里，而不是直接崩溃。"""
        self.resultBox.setPlainText(
            "参数计算出现异常，已保持上一次的显示结果。\n\n"
            f"异常类型：{type(exc).__name__}\n"
            f"异常信息：{exc}\n\n"
            "请检查 fr、纵轴上限等输入是否为合理数值。"
        )

    # ------------------------------------------------------------------
    # 读取当前控件的最新参数（读取，不修改）
    # ------------------------------------------------------------------
    def _read_params(self):
        k_ratio = _lin_from_slider(self.sliderK.value(), K_MIN, K_MAX)
        q_cur = _log_from_slider(self.sliderQ.value(), Q_MIN, Q_MAX)
        fn_work = _log_from_slider(self.sliderFn.value(), FN_MIN, FN_MAX)

        try:
            fr_khz = float(self.editFr.value())
            if not math.isfinite(fr_khz) or fr_khz <= 0:
                raise ValueError
        except (TypeError, ValueError):
            fr_khz = DEFAULT_FR_KHZ

        try:
            y_max = float(self.editYmax.value())
            if not math.isfinite(y_max) or y_max <= 0:
                raise ValueError
        except (TypeError, ValueError):
            y_max = DEFAULT_YMAX

        return k_ratio, q_cur, fn_work, fr_khz, y_max

    # ------------------------------------------------------------------
    # 核心刷新逻辑：按 dirty flag 增量计算，只更新数据
    # ------------------------------------------------------------------
    def _apply_update(self) -> None:
        k_ratio, q_cur, fn_work, fr_khz, y_max = self._read_params()

        # 依据 dirty 组合决定 refresh 的增量参数
        k = self.dirty_k
        q = self.dirty_q
        fn = self.dirty_fn
        fr = self.dirty_fr
        ylim = self.dirty_ylim

        # 示例场景后续刷新当前值
        self._clear_dirty()

        stamp = None
        if self._perf_log:
            import time as _time
            stamp = _time.perf_counter()

        values = self.plot.refresh(
            k=k, q=q, fn=fn, fr=fr, ylim=ylim,
            k_ratio=k_ratio, Q=q_cur, fn_work=fn_work,
            fr_khz=fr_khz, y_max=y_max,
        )

        if self._perf_log:
            import time as _time
            compute_ms = (_time.perf_counter() - stamp) * 1000.0
            self._record_perf(k, q, fn, compute_ms)

        # 数值标签
        self.labelK.setText(f"{k_ratio:.3f}")
        self.labelQ.setText(f"{q_cur:.4f}")
        self.labelFn.setText(f"{fn_work:.4f}")

        # 顶部标题状态栏：固定标题 + 动态参数
        self.statusLabel.setText(
            f"K={k_ratio:.4f}    Q={q_cur:.4f}    fn={fn_work:.4f}"
            f"    fs={fn_work * fr_khz:.3f} kHz"
            f"    fr={fr_khz:.3f} kHz"
        )

        # 右侧结果区：只有内容变化时才更新
        text = format_result_text(values)
        if text != self._last_applied:
            self.resultBox.setPlainText(text)
            self._last_applied = text

        # 记录刷新耗时
        draw_stamp = None
        if self._perf_log:
            import time as _time
            draw_stamp = _time.perf_counter()

        self.canvas.update()

        if self._perf_log:
            import time as _time
            self._perf["draw_sum"] += (_time.perf_counter() - draw_stamp) * 1000.0
            self._perf["frames"] += 1

    def _clear_dirty(self):
        self.dirty_k = False
        self.dirty_q = False
        self.dirty_fn = False
        self.dirty_fr = False
        self.dirty_ylim = False

    def _record_perf(self, k, q, fn, ms):
        p = self._perf
        if k:
            p["k_sum"] += ms
            p["k_n"] += 1
        elif q:
            p["q_sum"] += ms
            p["q_n"] += 1
        elif fn:
            p["fn_sum"] += ms
            p["fn_n"] += 1

    def _dump_perf(self):
        if not self._perf_log or self._perf is None:
            return
        p = self._perf
        frames = max(p["frames"], 1)
        wall_s = self._elapsed.elapsed() / 1000.0
        fps = frames / wall_s if wall_s > 0 else 0.0
        k_avg = p["k_sum"] / p["k_n"] if p["k_n"] else 0.0
        q_avg = p["q_sum"] / p["q_n"] if p["q_n"] else 0.0
        fn_avg = p["fn_sum"] / p["fn_n"] if p["fn_n"] else 0.0
        print(
            f"[perf] compute: K={k_avg:.2f}ms Q={q_avg:.2f}ms fn={fn_avg:.2f}ms "
            f"draw={p['draw_sum']/frames:.2f}ms fps={fps:.1f} "
            f"frames={p['frames']} wall={wall_s:.2f}s",
            file=sys.stderr,
        )


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    _timing_mark("t1_qapp")
    family = qt_font_family()
    if family:
        app.setFont(QFont(family, 9))

    win = MainWindow()
    _timing_mark("t2_mainwin")
    win.show()
    _timing_mark("t3_show")

    if _TIMING_ENABLED:
        # 定时模式：等“首个真实 paint 落地 + 事件循环再兜一圈”才真正算可交互，
        # 再由 t5_event_loop_ready 之后的 settle 延迟触发自动退出。
        _marker = _ReadyMarker(app)
        _marker.install(win.canvas)
        app.installEventFilter(_marker)

    return app.exec()


if __name__ == "__main__":
    if _TIMING_ENABLED:
        _timing_mark("t0_entry")

    sys.exit(main())