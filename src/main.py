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
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QSlider,
    QToolButton,
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
)
# ---- 工程设计数学层（Phase 2/3/4 产物，见需求 14~23） ----
from llc_design import (  # noqa: E402
    DesignSpec,
    compute_design,
    recommend_q,
    validate_spec,
)
from llc_solver import solve_gain_frequency  # noqa: E402
from llc_stress import (  # noqa: E402
    cr_stress,
    fha_phasor,
    secondary_currents,
)
from llc_report import (  # noqa: E402
    format_key_results,
    format_detail_results,
    format_short_analysis,
    format_short_suggestions,
)

APP_TITLE = "LLC 谐振变换器交互式多增益曲线"

# ---- 工程设计默认值（Phase 6） ----
# 次级整流形式 -> 内部键（ct_diode/ct_sr/fb_diode/fb_sr）
# 显示文本为中文；内部键保持英文，中文化不影响计算逻辑（需求 2）
RECT_OPTIONS = [
    ("中心抽头二极管整流", "ct_diode"),
    ("中心抽头同步整流", "ct_sr"),
    ("全桥二极管整流", "fb_diode"),
    ("全桥同步整流", "fb_sr"),
]
#: 拓扑显示文本（内部键 half/full 不变，需求 2）
BRIDGE_OPTIONS = [("半桥", "half"), ("全桥", "full")]
#: 过载倍率选项（显示标签 -> 倍率）
OVERLOAD_OPTIONS = [("100%", 1.0), ("110%", 1.1), ("120%", 1.2)]
DEFAULT_VIN_MIN, DEFAULT_VIN_NOM, DEFAULT_VIN_MAX = 300.0, 390.0, 480.0
DEFAULT_VO, DEFAULT_POUT, DEFAULT_IO = 12.0, 600.0, 50.0
DEFAULT_ETA, DEFAULT_VF, DEFAULT_N = 0.92, 0.5, 16.0

# 滑块使用整数刻度模拟连续/对数取值
SLIDER_STEPS = 1000

#: 拖动期间刷新合并间隔（毫秒）。16 ms ≈ 60 FPS；33 ms ≈ 30 FPS。
REFRESH_MS = 16

#: 工程参数键盘输入自动提交 debounce（毫秒，需求 4）：停止输入一段时间后
#: interpretText → 校验 → 全部有效才 commit → 自动重新计算。
ENG_DEBOUNCE_MS = 300

#: 拖动期间完整工程结果/长文本节流刷新间隔（毫秒，需求 5.3/6.2）：
#: 拖动时曲线实时更新，完整工程计算与结果文本按此频率刷新，松手立即最终刷新。
RESULT_THROTTLE_MS = 120

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
        self.resize(1420, 960)
        self.setMinimumSize(1040, 820)

        # ---- 状态 ----
        self._updating = False          # 回调重入锁
        self._pending = False

        # ---- 拖动节流状态（需求 5.3 / 6.2 / 6.3） ----
        self._dragging = False          # 滑块拖动中：曲线实时、工程/长文本降频
        self._engine_pending = False    # 拖动中需要重算工程（交给节流/松手刷新）
        self._result_timer = QTimer(self)
        self._result_timer.setSingleShot(True)
        self._result_timer.setInterval(RESULT_THROTTLE_MS)
        self._result_timer.timeout.connect(self._on_result_timer)

        # ---- 工程参数键盘输入自动提交（需求 4） ----
        self._eng_debounce = QTimer(self)
        self._eng_debounce.setSingleShot(True)
        self._eng_debounce.setInterval(ENG_DEBOUNCE_MS)
        self._eng_debounce.timeout.connect(self._on_eng_debounce)
        self._eng_debounce_sender = None

        # ---- 工程设计事务式状态（Phase 6，需求二十六） ----
        self._engine_dirty = True       # 工程设计输入变化需要重算
        self._engine_ok = False         # 最近一次工程设计是否有效
        self._engine = None             # 最近有效工程设计结果 dict
        self._stress = None             # 最近有效 FHA 应力 dict
        self._engine_error = None       # 最近一次设计错误信息（出现则保留旧结果）
        self._sync_io_vo = False        # Pout/Io/Vo 联动重入锁
        self._auto_q_sync = False       # 推荐 Q 写回滑块重入锁

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

        # 右侧：默认【关键结果】精简区 + 可展开"详细信息"（需求 5.1）
        right_col = QVBoxLayout()
        right_col.setSpacing(3)
        self.resultBox = QPlainTextEdit()
        self.resultBox.setReadOnly(True)
        self.resultBox.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.resultBox.setMinimumWidth(330)
        self.resultBox.setMaximumWidth(430)
        self.resultBox.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        mono = QFont(qt_font_family() or "Consolas", 10)
        self.resultBox.setFont(mono)
        right_col.addWidget(self.resultBox, stretch=1)

        self.detailToggle = QToolButton()
        self.detailToggle.setText("详细信息 ▼")
        self.detailToggle.setCheckable(True)
        self.detailToggle.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.detailToggle.setAutoRaise(True)
        self.detailToggle.setStyleSheet("text-align:left; color:#555;")
        self.detailToggle.toggled.connect(self._on_detail_toggle)
        right_col.addWidget(self.detailToggle, stretch=0)

        self.detailBox = QPlainTextEdit()
        self.detailBox.setReadOnly(True)
        self.detailBox.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.detailBox.setMinimumWidth(330)
        self.detailBox.setMaximumWidth(430)
        self.detailBox.setMinimumHeight(120)
        self.detailBox.setMaximumHeight(280)
        self.detailBox.setFont(mono)
        self.detailBox.setVisible(False)
        right_col.addWidget(self.detailBox, stretch=0)

        upper.addLayout(right_col, stretch=1)

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

        # ---------- 底部第二行：工程设计参数 + 显示选项 ----------
        eng_row = QHBoxLayout()
        eng_row.setSpacing(8)

        # --- 工程设计参数面板（Phase 6，需求十一） ---
        eng_panel = QGroupBox("工程设计参数（FHA estimate）")
        eng_panel.setFont(QFont(qt_font_family() or "", 10, QFont.Bold))
        egrid = QGridLayout(eng_panel)
        egrid.setContentsMargins(10, 12, 10, 8)
        egrid.setHorizontalSpacing(8)
        egrid.setVerticalSpacing(5)
        r = 0

        def spin(dec, lo, hi, val, st=1.0, w=76):
            sb = QDoubleSpinBox()
            sb.setDecimals(dec)
            sb.setRange(lo, hi)
            sb.setValue(val)
            sb.setSingleStep(st)
            sb.setKeyboardTracking(False)
            sb.setMinimumWidth(w)
            return sb

        # 行 0：Vin_min / Vin_nom / Vin_max
        for col, (lbl, sb) in enumerate([
            ("Vin_min/V", None), ("Vin_nom/V", None), ("Vin_max/V", None)]):
            egrid.addWidget(QLabel(lbl), r, col * 2)
        self.spinVinMin = spin(1, 1.0, 1e5, DEFAULT_VIN_MIN, 5.0)
        self.spinVinNom = spin(1, 1.0, 1e5, DEFAULT_VIN_NOM, 5.0)
        self.spinVinMax = spin(1, 1.0, 1e5, DEFAULT_VIN_MAX, 5.0)
        for col, sb in enumerate((self.spinVinMin, self.spinVinNom, self.spinVinMax)):
            egrid.addWidget(sb, r, col * 2 + 1)
        r += 1

        # 行 1：Vo / Pout / Io
        egrid.addWidget(QLabel("Vo/V"), r, 0)
        self.spinVo = spin(2, 0.1, 1e4, DEFAULT_VO, 1.0)
        egrid.addWidget(self.spinVo, r, 1)
        egrid.addWidget(QLabel("Pout/W"), r, 2)
        self.spinPout = spin(1, 0.1, 1e7, DEFAULT_POUT, 10.0)
        egrid.addWidget(self.spinPout, r, 3)
        egrid.addWidget(QLabel("Io/A"), r, 4)
        self.spinIo = spin(2, 0.01, 1e6, DEFAULT_IO, 1.0)
        egrid.addWidget(self.spinIo, r, 5)
        r += 1

        # 行 2：拓扑 / 整流
        egrid.addWidget(QLabel("拓扑"), r, 0)
        self.comboBridge = QComboBox()
        self.comboBridge.addItems([t for t, _ in BRIDGE_OPTIONS])
        self.comboBridge.setCurrentIndex(0)
        egrid.addWidget(self.comboBridge, r, 1)
        egrid.addWidget(QLabel("次级整流"), r, 2)
        self.comboRect = QComboBox()
        self.comboRect.addItems([t for t, _ in RECT_OPTIONS])
        self.comboRect.setCurrentIndex(1)   # 中心抽头同步整流
        egrid.addWidget(self.comboRect, r, 3, 1, 3)
        r += 1

        # 行 3：匝比 / Q 模式
        egrid.addWidget(QLabel("匝比"), r, 0)
        self.comboTurn = QComboBox()
        self.comboTurn.addItems(["自动", "手动"])
        self.comboTurn.setCurrentIndex(0)
        egrid.addWidget(self.comboTurn, r, 1)
        self.spinN = spin(3, 0.01, 1e4, DEFAULT_N, 0.5, 76)
        self.spinN.setEnabled(False)
        egrid.addWidget(self.spinN, r, 2)
        egrid.addWidget(QLabel("Q 模式"), r, 3)
        self.comboQMode = QComboBox()
        self.comboQMode.addItems(["手动", "自动推荐"])
        self.comboQMode.setCurrentIndex(0)
        egrid.addWidget(self.comboQMode, r, 4, 1, 2)
        r += 1

        # 行 4：效率 / Vf / 过载
        egrid.addWidget(QLabel("η"), r, 0)
        self.spinEta = spin(3, 0.01, 1.0, DEFAULT_ETA, 0.01, 64)
        egrid.addWidget(self.spinEta, r, 1)
        egrid.addWidget(QLabel("Vf(V)"), r, 2)
        self.spinVdrop = spin(3, 0.0, 5.0, DEFAULT_VF, 0.05, 64)
        egrid.addWidget(self.spinVdrop, r, 3)
        egrid.addWidget(QLabel("过载"), r, 4)
        self.comboOverload = QComboBox()
        self.comboOverload.addItems([t for t, _ in OVERLOAD_OPTIONS])
        self.comboOverload.setCurrentIndex(1)   # 110%
        egrid.addWidget(self.comboOverload, r, 5)
        r += 1

        # 行 5：键盘输入自动应用状态（需求 4，轻量提示）
        self.engStatusLabel = QLabel("")
        self.engStatusLabel.setStyleSheet("color:#888; font-size:9pt;")
        egrid.addWidget(self.engStatusLabel, r, 0, 1, 6)
        eng_row.addWidget(eng_panel, stretch=1)

        # --- 显示选项面板（Phase 8，需求四） ---
        disp_panel = QGroupBox("显示选项")
        disp_panel.setFont(QFont(qt_font_family() or "", 10, QFont.Bold))
        dbox = QVBoxLayout(disp_panel)
        dbox.setContentsMargins(10, 10, 10, 8)
        dbox.setSpacing(4)
        self.cbRefQ = QCheckBox("预设参考 Q 曲线")
        self.cbRefQ.setChecked(True)
        self.cbBoundary = QCheckBox("阻容分界线")
        self.cbBoundary.setChecked(True)
        self.cbMRange = QCheckBox("Mmin ~ Mmax 范围")
        self.cbMRange.setChecked(False)
        self.cbFnRange = QCheckBox("fnmin ~ fnmax 范围")
        self.cbFnRange.setChecked(False)
        for w in (self.cbRefQ, self.cbBoundary, self.cbMRange, self.cbFnRange):
            dbox.addWidget(w)
        note = QLabel("恒显：当前 Q / fnp / fnr=1 / 工作点 fn / 增益峰值",
                      wordWrap=False)
        note.setStyleSheet("color:#666;")
        dbox.addWidget(note)
        dbox.addStretch(1)
        eng_row.addWidget(disp_panel, stretch=0)

        root.addLayout(eng_row, stretch=0)

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
        # 按下时进入拖动节流模式（需求 5.3 / 6.2）
        self.sliderK.sliderPressed.connect(self._on_slider_pressed)
        self.sliderQ.sliderPressed.connect(self._on_slider_pressed)
        self.sliderFn.sliderPressed.connect(self._on_slider_pressed)

        # ---------- 工程设计参数信号（Phase 6，事务式） ----------
        for w in (self.spinVinMin, self.spinVinNom, self.spinVinMax,
                  self.spinVo, self.spinPout, self.spinIo,
                  self.spinN, self.spinEta, self.spinVdrop):
            w.valueChanged.connect(self._on_eng_spin)
            # 键盘输入自动提交（需求 4）：textEdited 启动 debounce，
            # editingFinished（Enter/失焦）立即提交。
            w.lineEdit().textEdited.connect(self._on_eng_text_edited)
            w.editingFinished.connect(self._on_eng_editing_finished)
        self.comboBridge.currentIndexChanged.connect(self._on_eng_changed)
        self.comboRect.currentIndexChanged.connect(self._on_eng_changed)
        self.comboTurn.currentIndexChanged.connect(self._on_turn_changed)
        self.comboQMode.currentIndexChanged.connect(self._on_qmode_changed)
        self.comboOverload.currentIndexChanged.connect(self._on_eng_changed)
        # 匝比自动/手动：手动时启用 n 输入
        self._apply_turn_enabled()

        # ---------- 显示选项信号（Phase 8，需求四/八） ----------
        self.cbRefQ.stateChanged.connect(self._on_display_changed)
        self.cbBoundary.stateChanged.connect(self._on_display_changed)
        self.cbMRange.stateChanged.connect(self._on_display_changed)
        self.cbFnRange.stateChanged.connect(self._on_display_changed)

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

    def _on_slider_pressed(self, *_):
        """滑块按下：进入拖动节流模式（需求 5.3 / 6.2）+ 参考族 preview 采样（需求 6.4）。

        拖动期间曲线/顶部状态实时更新；完整工程计算与长结果文本按
        ``RESULT_THROTTLE_MS`` 节流，松手时立即最终刷新。
        """
        self._dragging = True
        self.plot.set_preview(True)

    def _on_result_timer(self):
        """拖动节流计时器：做一次完整工程计算 + 长结果文本刷新。"""
        self._do_update(force_full=True)

    def _on_released(self, *_):
        """滑块释放：退出拖动节流，立即做一次全量最终刷新。

        拖动期间 valueChanged 已把最新目标参数写入各自 dirty flag；若最后一个
        valueChanged 还未被合并计时器 flush，这里补一次；若已 flush，则各 dirty
        均为 False，执行一次极轻量的纯文本/元数据刷新即可。绝不在这里全量重算
        曲线族，避免"松手顿一下"。
        """
        self._dragging = False
        self.plot.set_preview(False)
        self._result_timer.stop()
        if self._perf_log and self._perf:
            self._dump_perf()
        self._refresh_timer.stop()
        self._do_update(force_full=True)

    # ------------------------------------------------------------------
    # 工程设计/显示回调（Phase 6/8）
    # ------------------------------------------------------------------
    def _apply_turn_enabled(self):
        manual = self.comboTurn.currentIndex() == 1
        self.spinN.setEnabled(manual)
        if not manual:
            # 自动模式：显示由设计层算出的理论匝比
            self.spinN.setValue(self._engine["n"] if self._engine else DEFAULT_N)

    def _on_eng_spin(self, *_):
        # Pout = Vo × Io 联动（需求十一），用重入锁避免成环
        if not self._sync_io_vo:
            self._sync_io_vo = True
            try:
                s = self.sender()
                vo = self.spinVo.value()
                if s is self.spinPout or s is self.spinIo:
                    pout = self.spinPout.value()
                    io = self.spinIo.value()
                    if s is self.spinPout:
                        self.spinIo.setValue(pout / vo if vo > 0 else 0.0)
                    else:
                        self.spinPout.setValue(io * vo)
            finally:
                self._sync_io_vo = False
        self._engine_dirty = True
        self._schedule_refresh()

    def _on_eng_changed(self, *_):
        self._engine_dirty = True
        self._schedule_refresh()

    # ---- 键盘输入自动提交（需求 4） ----
    def _on_eng_text_edited(self, *_):
        """键盘输入中：显示"未完成"状态并启动 debounce。

        ``setKeyboardTracking(False)`` 下 valueChanged 只在失焦/Enter 才触发；
        这里用 lineEdit.textEdited 感知键盘编辑，停止输入一段时间后自动提交，
        无需再点击其他输入框。
        """
        le = self.sender()
        sb = le.parent() if le is not None else None
        self._eng_debounce_sender = sb
        self._set_eng_status("参数有未完成输入")
        self._eng_debounce.start()

    def _on_eng_debounce(self):
        """停止输入一段时间后：interpretText → 校验 → 自动提交。

        ``interpretText()`` 会把当前文本解析为数值；若值变化会自动触发
        ``valueChanged`` → ``_on_eng_spin`` → 事务式校验 → 重新计算。
        输入尚未完成或暂时非法时，事务式校验保留上一套有效结果，不覆盖。
        """
        sb = self._eng_debounce_sender
        self._eng_debounce_sender = None
        if sb is not None:
            sb.interpretText()
        self._set_eng_status("已自动应用")

    def _on_eng_editing_finished(self, *_):
        """Enter / 失焦：立即提交，不等 debounce。

        ``setKeyboardTracking(False)`` 下 valueChanged 只在失焦/Enter 才触发；
        这里显式 ``interpretText()`` 把当前文本解析为数值（若变化会触发
        ``valueChanged`` → ``_on_eng_spin`` → 事务式校验 → 重新计算），
        保证 Enter 立即生效、无需再点其他输入框（需求 4）。
        """
        self._eng_debounce.stop()
        sb = self.sender() or self._eng_debounce_sender
        self._eng_debounce_sender = None
        if sb is not None:
            sb.interpretText()
        self._set_eng_status("已自动应用")

    def _set_eng_status(self, text: str) -> None:
        if hasattr(self, "engStatusLabel"):
            self.engStatusLabel.setText(text)

    def _on_detail_toggle(self, checked: bool) -> None:
        """详细信息展开/折叠（需求 5.1）。"""
        self.detailBox.setVisible(checked)
        self.detailToggle.setText("详细信息 ▲" if checked else "详细信息 ▼")

    def _on_turn_changed(self, *_):
        self._apply_turn_enabled()
        self._engine_dirty = True
        self._schedule_refresh()

    def _on_qmode_changed(self, *_):
        self._engine_dirty = True
        self._schedule_refresh()

    def _on_display_changed(self, *_):
        """显示开关：只改显示状态，不触发任何无关数学重算（需求八/二十七/二十八）。"""
        self.plot.set_display_state(
            show_reference=self.cbRefQ.isChecked(),
            show_boundary=self.cbBoundary.isChecked(),
            show_m_range=self.cbMRange.isChecked() and self._engine_ok,
            show_fn_range=self.cbFnRange.isChecked() and self._engine_ok,
        )

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

    def _do_update(self, force_full: bool = False):
        """同步执行一次刷新（也用于滑块释放、初始和测试）。

        ``force_full``：拖动节流期间（``self._dragging``）默认只做轻量更新
        （曲线/顶部状态/数值标签），完整工程计算与长结果文本交给
        ``_result_timer`` 或滑块释放时的最终刷新（需求 5.3 / 6.2 / 6.3）。
        """
        if self._updating:
            self._pending = True
            return
        self._updating = True
        try:
            self._apply_update(force_full=force_full)
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
    def _apply_update(self, force_full: bool = False) -> None:
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

        # ---- 工程设计与应力（事务式：需求二十六；显示/数学状态分离：需求二十七） ----
        # 只有 K/Q/fr 或工程输入变化才重算设计层，纯 fn 拖动零重算。
        # 拖动节流（需求 6.2）：拖动期间只记录 pending，完整工程计算交给
        # _result_timer（约 8 FPS）或滑块释放时的最终刷新。
        if self._dragging and not force_full:
            if self._engine_dirty or k or q or fr:
                self._engine_pending = True
        else:
            if self._engine_dirty or k or q or fr or self._engine_pending:
                self._engine_dirty = False
                self._engine_pending = False
                self._recompute_engine(k_ratio, q_cur, fr_khz)
        self._apply_eng_availability()

        # 数值标签
        self.labelK.setText(f"{k_ratio:.3f}")
        self.labelQ.setText(f"{q_cur:.4f}")
        self.labelFn.setText(f"{fn_work:.4f}")

        # 顶部标题状态栏：固定标题 + 动态参数（含 M(fn)，拖动时实时更新）
        self.statusLabel.setText(
            f"K={k_ratio:.4f}    Q={q_cur:.4f}    fn={fn_work:.4f}"
            f"    M(fn)={values.get('Mfn', float('nan')):.4f}"
            f"    fs={fn_work * fr_khz:.3f} kHz"
            f"    fr={fr_khz:.3f} kHz"
        )

        # ---- 右侧结果区（需求 5.1 / 5.2 / 5.3 / 6.3） ----
        if self._dragging and not force_full:
            # 拖动中：不每帧重建长文本；交给 _result_timer 节流刷新。
            if not self._result_timer.isActive():
                self._result_timer.start()
        else:
            self._update_result_text(values)

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

    # ------------------------------------------------------------------
    # 右侧结果文本（需求 5.1 分层 + 5.2 滚动位置保持）
    # ------------------------------------------------------------------
    def _snapshot_result_scroll(self) -> dict:
        vsb = self.resultBox.verticalScrollBar()
        hsb = self.resultBox.horizontalScrollBar()
        return {
            "v": vsb.value(),
            "at_bottom": vsb.maximum() > 0 and vsb.value() >= vsb.maximum() - 1,
            "h": hsb.value(),
        }

    def _restore_result_scroll(self, snap: dict) -> None:
        vsb = self.resultBox.verticalScrollBar()
        hsb = self.resultBox.horizontalScrollBar()
        if snap["at_bottom"]:
            vsb.setValue(vsb.maximum())
        else:
            vsb.setValue(min(snap["v"], vsb.maximum()))
        hsb.setValue(min(snap["h"], hsb.maximum()))

    def _set_result_text(self, box: QPlainTextEdit, text: str) -> None:
        """设置文本并保持滚动位置（需求 5.2）：不因参数变化跳回顶部。"""
        snap = self._snapshot_result_scroll() if box is self.resultBox else None
        box.setPlainText(text)
        if snap is not None:
            self._restore_result_scroll(snap)

    def _update_result_text(self, values: dict) -> None:
        """默认【关键结果】精简区 + 精简分析/建议；详细信息在可展开区。"""
        text = format_key_results(values, self._engine, self._stress)
        if self._engine_ok and self._engine and self._stress:
            text += "\n\n" + format_short_analysis(self._engine, self._stress)
            text += "\n\n" + format_short_suggestions(self._engine)
        elif self._engine_error:
            text += "\n\n⚠ 工程参数无效：{:}\n（已保留上一套有效结果，输入会标红提示）".format(
                self._engine_error)
        if text != self._last_applied:
            self._set_result_text(self.resultBox, text)
            self._last_applied = text
        # 详细信息区（若已展开）同步刷新：以开关状态为准（isVisible 依赖窗口显示，
        # 离屏测试/未 show 时不可靠）
        if self.detailToggle.isChecked():
            self._set_result_text(
                self.detailBox,
                format_detail_results(values, self._engine, self._stress))

    def _clear_dirty(self):
        self.dirty_k = False
        self.dirty_q = False
        self.dirty_fn = False
        self.dirty_fr = False
        self.dirty_ylim = False

    # ------------------------------------------------------------------
    # 工程设计事务式计算（Phase 6/7，需求二十六）
    # ------------------------------------------------------------------
    def _recompute_engine(self, k_ratio: float, q_cur: float, fr_khz: float) -> bool:
        """读取全部工程输入 → 校验 → 全量计算 → 全部成功才 commit。

        任一环节失败则保留上一套有效结果并把错误写入 ``_engine_error``。
        返回本次是否计算成功并已 commit。
        """
        bridge = "half" if self.comboBridge.currentIndex() == 0 else "full"
        rect = RECT_OPTIONS[self.comboRect.currentIndex()][1]
        vin_min = float(self.spinVinMin.value())
        vin_nom = float(self.spinVinNom.value())
        vin_max = float(self.spinVinMax.value())
        vo = float(self.spinVo.value())
        pout = float(self.spinPout.value())
        overload = OVERLOAD_OPTIONS[self.comboOverload.currentIndex()][1]
        eta = float(self.spinEta.value())
        vdrop = float(self.spinVdrop.value())
        turn_mode = "manual" if self.comboTurn.currentIndex() == 1 else "auto"
        n_manual = float(self.spinN.value())
        auto_q = self.comboQMode.currentIndex() == 1
        fr_hz = fr_khz * 1000.0

        def _spec(q_sel):
            return DesignSpec(
                bridge=bridge, rect=rect,
                vin_min=vin_min, vin_nom=vin_nom, vin_max=vin_max,
                vo=vo, pout=pout, vdrop=vdrop, efficiency=eta,
                overload=overload, turn_mode=turn_mode, n_manual=n_manual,
                fr_hz=fr_hz, k=k_ratio, q_selected=q_sel,
            )

        try:
            errs = validate_spec(_spec(q_cur))
            if errs:
                raise ValueError("；".join(errs))

            # 第一遍：仅需 n/M_req（用于自动推荐 Q）
            d0 = compute_design(_spec(q_cur))

            q_sel = q_cur
            if auto_q:
                q_sel = float(min(max(
                    recommend_q(k_ratio, d0["M_req_max"], margin=0.10),
                    Q_MIN), Q_MAX))
                # 推荐 Q 写回滑块（非强制，用户可手动改/切手动模式）
                sv = _slider_from_log(q_sel, Q_MIN, Q_MAX)
                sv = min(max(sv, 0), SLIDER_STEPS)
                if sv != self.sliderQ.value() and not self._auto_q_sync:
                    self._auto_q_sync = True
                    try:
                        self.sliderQ.blockSignals(True)
                        self.sliderQ.setValue(sv)
                        self.sliderQ.blockSignals(False)
                        self.dirty_q = True       # 下一轮重画当前 Q 曲线
                    finally:
                        self._auto_q_sync = False

            s = _spec(q_sel)
            errs = validate_spec(s)
            if errs:
                raise ValueError("；".join(errs))
            d = compute_design(s)

            # fn_min（Q_overload @ M_req_max）/ fn_max（Q_full @ M_req_min）
            sol = solve_gain_frequency(
                k=k_ratio,
                q_min_branch=d["Q_overload"], m_req_max=d["M_req_max"],
                q_max_branch=d["Q_full"], m_req_min=d["M_req_min"],
            )
            fn_min = float(sol["fn_min"])
            fn_max = float(sol["fn_max"])

            # 最劣工况 FHA 相量：低输入 + 过载 @ fn_min、Q_overload 曲线
            ph = fha_phasor(
                vin_min, fn_min * fr_hz if math.isfinite(fn_min) else fr_hz,
                d["Lr_calc"], d["Lm_calc"], d["Cr_calc"],
                d["Re_overload"], bridge,
            )
            pout_ol = pout * overload
            io_dc = pout_ol / vo if vo > 0 else 0.0
            sec = secondary_currents(rect, ph["ioe_rms"], d["n"], io_dc)
            crs = cr_stress(ph["ir_rms"], ph["omega"], d["Cr_calc"],
                            vin_min, bridge)

            ds_min = fn_min * fr_khz if math.isfinite(fn_min) else float("nan")
            ds_max = fn_max * fr_khz if math.isfinite(fn_max) else float("nan")

            engine = {
                "bridge": bridge, "rect": rect,
                "n_mode": d["n_mode"], "n": d["n"], "n_auto": d["n_auto"],
                "efficiency": eta,
                "vin_min": vin_min, "vin_nom": vin_nom, "vin_max": vin_max,
                "Pout_overload": pout_ol,
                "RL_full": d["RL_full"], "Re_full": d["Re_full"],
                "Zr_calc": d["Zr_calc"],
                "Lr_calc": d["Lr_calc"], "Lm_calc": d["Lm_calc"],
                "Cr_calc": d["Cr_calc"],
                "M_req_min": d["M_req_min"], "M_req_nom": d["M_req_nom"],
                "M_req_max": d["M_req_max"],
                "Q_full": d["Q_full"], "Q_overload": d["Q_overload"],
                "Q_auto": q_sel,
                "fn_min": fn_min, "fn_max": fn_max,
                "fs_min": ds_min, "fs_max": ds_max,
                "M_available": float(sol["M_boundary"]),
                "fn_boundary": float(sol["fn_boundary"]),
                "fn_min_feasible": bool(sol["fn_min_feasible"]),
                "fn_max_feasible": bool(sol["fn_max_feasible"]),
                "fn_min_reason": sol["fn_min_reason"],
                "auto_q": auto_q,
                "tank": {},
                "cr": crs,
            }
            stress = {
                "ioe_rms": ph["ioe_rms"],
                "im_rms": ph["im_rms"],
                "ir_rms": ph["ir_rms"],
                "ir_peak": ph["ir_peak"],
                "secondary": sec, "cr": crs,
            }

            # ---- commit（事务式：全部成功才提交） ----
            self._engine = engine
            self._stress = stress
            self._engine_error = None
            self._engine_ok = True
            # 显示范围带只从有效结果刷新（显示/数学分离）
            self.plot.set_display_state(
                m_req_min=d["M_req_min"], m_req_max=d["M_req_max"],
                fn_min=(fn_min if sol["fn_min_feasible"] else float("nan")),
                fn_max=(fn_max if sol["fn_max_feasible"] else float("nan")),
            )
            # 自动匝比：把理论 n 显示到控件
            if turn_mode != "manual":
                target = float(d["n_auto"])
                if abs(self.spinN.value() - target) > max(1e-4, target * 1e-4):
                    self.spinN.blockSignals(True)
                    self.spinN.setValue(target)
                    self.spinN.blockSignals(False)
            return True
        except Exception as exc:
            # 失败：保留上一套有效结果，仅记录错误（需求二十六）
            self._engine_ok = False
            self._engine_error = str(exc)
            return False

    def _apply_eng_availability(self):
        """工程参数未完整/无效时：M 范围与 fn 范围开关灰显不可用（需求四）。"""
        ok = self._engine_ok
        for cb in (self.cbMRange, self.cbFnRange):
            if cb.isEnabled() != ok:
                cb.setEnabled(ok)

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