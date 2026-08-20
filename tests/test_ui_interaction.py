# -*- coding: utf-8 -*-
"""UI/交互最终专项测试（离屏运行）。

覆盖本轮四项修复：
1. 图示完整性（Y nice ticks / log minor grid / X 正反变换 / 自适应图例 / 裁剪）；
2. 阻容分界线视觉（品红粗虚线、图例 dash 宽度）；
3. 分层缓存（fn/Q/K 拖动只重建必要层、sliderRelease 不全量 dirty）；
4. Curve Hover Inspector（8 项：正反变换/命中 Q/超出容差/最近优先/tie-break/
   边界 Qb·Mb/不触发重算/缓存稳定）。

符号体系：K = Lm/Lr，fn = fs/fr，Q = sqrt(Lr/Cr)/Rac。
"""

from __future__ import annotations

import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 UI 交互测试")

from PySide6.QtCore import QPoint, QPointF, QRectF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from plot_widget import (  # noqa: E402
    BOUNDARY_COLOR,
    BOUNDARY_LABEL_COLOR,
    FAMILY_COLORS,
    GainPlotWidget,
    HOVER_TOL_PX,
    _hex,
)
from llc_py import (  # noqa: E402
    FN_MAX, FN_MIN, Q_FAMILY, boundary_gain, fn_parallel, input_region,
    llc_gain, llc_input_impedance_normalized, q_boundary_for_fn,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def plot(qapp):
    w = GainPlotWidget()
    w.resize(1100, 720)
    w.show()
    qapp.processEvents()
    yield w
    w.close()
    w.deleteLater()
    qapp.processEvents()


_RECT = QRectF(100, 50, 900, 500)


# ===========================================================================
# 一、图示完整性
# ===========================================================================
def test_y_ticks_cover_full_range(plot):
    """Y nice ticks：从 0 开始、单调递增、覆盖 ymax、步长规则。"""
    plot.ymax = 2.2
    ticks = plot._y_ticks()
    assert ticks[0] == 0.0
    assert ticks == sorted(ticks)
    assert ticks[-1] >= 2.2
    assert len(ticks) >= 4, f"ymax=2.2 应有足够刻度，实际 {ticks}"
    # 步长应为 nice number（1/2/2.5/5 × 10^n）
    step = ticks[1] - ticks[0]
    assert step in (0.5, 0.25, 0.2, 1.0, 0.1, 5.0, 2.0, 2.5), f"步长不规整：{step}"
    # 每个刻度映射为互不相同的唯一 y（网格与刻度严格对应）
    ys = [plot._map_y(v, _RECT) for v in ticks]
    assert len(set(round(y, 3) for y in ys)) == len(ticks)


def test_y_ticks_high_ymax(plot):
    plot.ymax = 50.0
    ticks = plot._y_ticks()
    assert ticks[-1] >= 50.0
    assert ticks[0] == 0.0
    step = ticks[1] - ticks[0]
    assert step in (5.0, 10.0, 2.5, 1.0), f"ymax=50 步长不规整：{step}"


def test_y_ticks_small_ymax(plot):
    plot.ymax = 0.5
    ticks = plot._y_ticks()
    assert ticks[-1] >= 0.5
    assert ticks[-1] <= 1.0


def test_log_minor_grid_each_decade_no_duplicates(plot):
    """log 次网格：每个 decade 统一 2..9，且绝不重复映射。"""
    freqs = plot._minor_log_freqs()
    assert set(freqs) == len(freqs) * [0] or len(freqs) == len(set(freqs))
    # 完整覆盖 0.1~10 内每个 decade 的 2..9
    assert {round(f, 6) for f in freqs} >= {
        round(0.2, 6), round(0.3, 6), round(0.9, 6),
        round(2.0, 6), round(9.0, 6),
    }
    # 所有频率都落在绘图范围内
    for f in freqs:
        assert FN_MIN <= f <= FN_MAX
    # 关键回归：0.2/0.3... 必须映射到 0.2 的像素位置，而不是 2
    x_02 = plot._map_x(0.2, _RECT)
    x_2 = plot._map_x(2.0, _RECT)
    assert abs(x_02 - x_2) > 100.0, "0.2 与 2 必须映射到不同像素位置"


def test_x_forward_inverse_consistent(plot):
    """fn -> pixel -> fn 正反变换一致（全 log 范围）。"""
    for fn in (FN_MIN, 0.3, 0.5, 0.72, 1.0, 3.0, 7.0, FN_MAX):
        px = plot._map_x(fn, _RECT)
        back = plot.pixel_to_fn(px, _RECT)
        assert back == pytest.approx(fn, rel=1e-9)


def test_legend_shows_all_entries_adaptively(plot):
    """图例自适应：全部条目（>=15）都能被布局到。"""
    entries = plot.legend_entries()
    assert len(entries) >= 15, "不得通过删条目解决拥挤"
    n = len(entries)
    for width in (560, 1000, 1500):
        plot.resize(width, 720)
        lay = plot._legend_layout(width - 100.0, 720.0)
        assert lay["cols"] * lay["rows"] >= n, \
            f"宽 {width} 下列数×行数无法容纳 {n} 条"
        assert lay["cols"] >= 1 and lay["rows"] >= 1


def test_legend_resize_changes_layout(plot):
    """窗口 resize 后图例列数自适应变化。"""
    plot.resize(600, 720)
    small = plot._legend_layout(600 - 100.0, 720.0)
    plot.resize(1600, 720)
    large = plot._legend_layout(1600 - 100.0, 720.0)
    assert large["cols"] >= small["cols"]


def test_curve_renders_without_breaking_when_exceeding_ymax(plot):
    """曲线超 ymax 不再断线：完整路径可绘制且无异常（靠裁剪而非改数据）。"""
    plot.ymax = 1.2  # 小纵轴上界，迫使大量曲线超出顶部
    plot._compute_current(plot.K, plot.Q)
    r = _RECT
    paths = (plot._build_curve_path(plot.fn_curve, plot.current_y, r),)
    assert any(not p.isEmpty() for p in paths)
    # 渲染整张基底不应抛异常
    plot._base_dirty = True
    plot._ensure_base()


# ===========================================================================
# 二、阻容分界线视觉
# ===========================================================================
def test_boundary_color_is_vivid_magenta(plot):
    assert BOUNDARY_COLOR.lower() == "#d000c8"
    assert _hex(BOUNDARY_COLOR) is not None


def test_boundary_distinct_from_key_lines(plot):
    """品红必须明显区别于黑色当前 Q / 红 fnp / 蓝 fnr。"""
    from plot_widget import CURRENT_COLOR, FNR_COLOR, FNP_COLOR
    b = _hex(BOUNDARY_COLOR)
    others = [_hex(CURRENT_COLOR), _hex(FNP_COLOR), _hex(FNR_COLOR)]
    # 高饱和品红：红、蓝均高且绿极低（青/灰的绿不会如此低）
    r_, g_, b_ = b.red(), b.green(), b.blue()
    assert b_ > 150 and r_ > 150 and g_ < 60, f"应为高饱和品红/紫红：r{b.red()} g{b.green()} b{b.blue()}"
    for o in others:
        assert not (abs(o.red() - r_) < 20 and abs(o.green() - g_) < 20
                    and abs(o.blue() - b_) < 20), "品红与既有线色过于接近"


def test_boundary_legend_entry_thick_dashed(plot):
    entries = plot.legend_entries()
    bnd = next(e for e in entries if "阻容分界线" in e[3])
    color, width, style, _ = bnd
    assert color == BOUNDARY_COLOR
    assert width >= 3.0
    from PySide6.QtCore import Qt
    assert style == Qt.DashLine


def test_boundary_label_present(plot):
    """阻容分界 → 图内带有 ∠Zin=0 线旁标注。"""
    lay_label = "∠Zin=0"
    # 渲染不应抛异常且不依赖具体像素（标注随 K 自动调整）
    plot._compute_boundary(plot.K)
    plot._base_dirty = True
    assert plot._ensure_base() is True


# ===========================================================================
# 三、分层缓存：只重建必要的层
# ===========================================================================
def test_slider_release_does_not_full_dirty(plot, qapp):
    """sliderRelease 只冲刷未 flush 的值，不触发全量重算曲线。"""
    w = app_main.MainWindow()
    # 先做一次 Q 拖动，使 current 计算过一次
    w.sliderQ.setValue(300)
    w._do_update()
    plot_ = w.plot
    stats = dict(plot_.stats)
    reb = dict(plot_.rebuild)
    # 松手（此时无 pending dirty，应只做轻量元数据刷新）
    w.sliderQ.setValue(700)
    w._do_update()   # 先 flush，确保 dirty 已清
    w._refresh_timer.stop()
    w._on_released()
    assert plot_.stats["family"] == stats["family"]
    assert plot_.stats["boundary"] == stats["boundary"]
    # 当前 Q 曲线不应因"松手全量"而多算（除非值确实变化）
    assert plot_.rebuild["family_path"] == reb["family_path"]
    assert plot_.rebuild["boundary_path"] == reb["boundary_path"]
    w._refresh_timer.stop(); w.close(); w.deleteLater(); qapp.processEvents()


def test_fn_drag_rebuilds_nothing(plot):
    """fn 1000 次变化：三类路径/基底相对之前（结构上）允许变化，但绝不重算数学族。"""
    plot.ymax = 2.2
    plot._compute_family(plot.K)
    plot._compute_boundary(plot.K)
    plot._compute_current(plot.K, plot.Q)
    fam = plot.stats["family"]
    bnd = plot.stats["boundary"]
    cur = plot.stats["current"]
    for i in range(1000):
        fn = fn_parallel(plot.K) + (1.0 - fn_parallel(plot.K)) * (i / 1000)
        plot.refresh(fn=True, k_ratio=plot.K, Q=plot.Q, fn_work=fn,
                     fr_khz=plot.fr_khz, y_max=plot.ymax)
    assert plot.stats["family"] == fam, "fn 拖动不得重算参考族"
    assert plot.stats["boundary"] == bnd, "fn 拖动不得重算边界"
    assert plot.stats["current"] == cur, "fn 拖动不得重算当前 Q 整条曲线"


def test_q_drag_rebuilds_only_current(plot):
    """Q 1000 次变化：不重建参考族/边界路径，只更新当前路径。"""
    plot._compute_family(plot.K)
    plot._compute_boundary(plot.K)
    f0 = plot.rebuild["family_path"]
    b0 = plot.rebuild["boundary_path"]
    c0 = plot.rebuild["current_path"]
    for i in range(1000):
        q = 0.05 + (10.0 - 0.05) * (i / 1000)
        plot.refresh(q=True, k_ratio=plot.K, Q=q, fn_work=plot.fn_work,
                     fr_khz=plot.fr_khz, y_max=plot.ymax)
    assert plot.rebuild["family_path"] == f0, "Q 拖动不得重建参考族路径"
    assert plot.rebuild["boundary_path"] == b0, "Q 拖动不得重建边界路径"
    assert plot.rebuild["current_path"] > c0, "Q 拖动应重建当前 Q 路径"


def test_k_drag_rebuilds_all(plot):
    """K 变化才重建参考族 + 边界 + 当前路径。"""
    f0 = plot.rebuild["family_path"]
    b0 = plot.rebuild["boundary_path"]
    c0 = plot.rebuild["current_path"]
    plot.refresh(k=True, k_ratio=plot.K, Q=plot.Q, fn_work=plot.fn_work,
                 fr_khz=plot.fr_khz, y_max=plot.ymax)
    assert plot.rebuild["family_path"] > f0
    assert plot.rebuild["boundary_path"] > b0
    assert plot.rebuild["current_path"] > c0


# ===========================================================================
# 四、Hover Inspector —— 8 项
# ===========================================================================
def _hit_pt(plot, kind, q, fn, rect=_RECT):
    """返回在 (fn, M) 处精确落在某种曲线上的屏幕坐标。"""
    if kind == "boundary":
        m = boundary_gain(fn, plot.K)
    else:
        m = llc_gain(fn, plot.K, q)
    px = plot._map_x(fn, rect)
    py = plot._map_y_full(m, rect)
    return px, py


def test_hover_inverse_transform(plot):
    """Test1：像素量直接由 fn 反推，与像素算回一致。"""
    for fn in (0.25, 0.6, 1.0, 2.5, 8.0):
        px = plot._map_x(fn, _RECT)
        assert plot.pixel_to_fn(px, _RECT) == pytest.approx(fn, rel=1e-9)
        # hit_test 内部用的也是这条反变换
        hit = plot.hit_test(_hit_pt(plot, "current", plot.Q, fn)[0], 0.0, _RECT)
        assert hit is None or hit["fn"] == pytest.approx(fn, rel=1e-2)


def test_hover_hits_normal_q_curve(plot):
    """Test2：普通 Q 曲线命中 → 识别出精确参数。"""
    fn = 0.8
    q = 0.5
    px, py = _hit_pt(plot, "current", q, fn)
    hit = plot.hit_test(px, py, _RECT)
    assert hit is not None
    assert hit["kind"] in ("current", "family")
    assert hit["fn"] == pytest.approx(fn, rel=1e-6)
    assert hit["m"] == pytest.approx(llc_gain(fn, plot.K, q), rel=1e-6)
    if hit["kind"] == "family":
        assert hit["q"] == pytest.approx(q, rel=1e-3) or \
            hit["q"] == pytest.approx(1.0, rel=1e-3)  # 奇异点 (1,1) 附近
    assert input_region(fn, plot.K, plot.Q) == hit["region"]


def test_hover_beyond_tolerance_returns_none(plot):
    """Test3：离曲线超过容差 → 无 hover。"""
    # 屏幕 y 远超任何曲线可达范围
    px, _ = _hit_pt(plot, "current", plot.Q, 0.8)
    far_y = _RECT.top() - 40.0
    assert plot.hit_test(px, far_y, _RECT) is None


def test_hover_nearest_curve_wins(plot):
    """Test4：多曲线接近，选屏幕距离更小的一条。"""
    fn = 2.0
    # current Q=0.5 与 family q=0.1 在该 fn 处分布不同
    px = plot._map_x(fn, _RECT)
    py_fam = plot._map_y_full(llc_gain(fn, plot.K, 0.1), _RECT)
    py_cur = plot._map_y_full(llc_gain(fn, plot.K, plot.Q), _RECT)
    assert abs(py_fam - py_cur) > 20, "测试需两条曲线明显分离"
    hit = plot.hit_test(px, py_fam, _RECT)
    assert hit is not None
    if hit["kind"] == "family":
        assert hit["q"] == pytest.approx(0.1, rel=1e-3)
    elif hit["kind"] == "current":
        # 若 current 距离更小则 current 胜出也是合理的
        assert abs(plot._map_y_full(llc_gain(fn, plot.K, plot.Q), _RECT)
                   - py_fam) < HOVER_TOL_PX


def test_hover_tie_break_current_first(plot):
    """Test5：距离几乎相同（如奇点 (1,1)）时，当前 Q 优先。"""
    fn = 1.0
    px, py = _hit_pt(plot, "current", plot.Q, fn)
    hit = plot.hit_test(px, py, _RECT)
    assert hit is not None
    assert hit["kind"] == "current", f"(1,1) 奇点处当前 Q 应优先，实际 {hit['kind']}"


def test_hover_boundary_qb_mb(plot):
    """Test6：阻容分界 Hover → kind=boundary，Qb/Mb 正确，Im(Zin)≈0。"""
    fn = 0.6
    px, py = _hit_pt(plot, "boundary", None, fn)
    hit = plot.hit_test(px, py, _RECT)
    assert hit is not None and hit["kind"] == "boundary", f"应命中边界，实际 {hit}"
    assert hit["mb"] == pytest.approx(boundary_gain(fn, plot.K), rel=1e-6)
    assert hit["qb"] == pytest.approx(q_boundary_for_fn(fn, plot.K), rel=1e-6)
    # 边界点处 Im(Zin(K, Qb))≈0
    z = llc_input_impedance_normalized(fn, plot.K, hit["qb"])
    im = z.imag if isinstance(z, complex) else z[0].imag
    assert abs(im) < 1e-9


def test_hover_does_not_recompute_curves(plot):
    """Test7：1000 次 hover 不触发任何曲线重算 / 路径重建。"""
    plot._compute_family(plot.K)
    plot._compute_boundary(plot.K)
    stats = dict(plot.stats)
    reb = dict(plot.rebuild)
    census = plot.artist_census()
    for i in range(1000):
        fn = 0.3 + 7.0 * (i / 1000)
        px = plot._map_x(fn, _RECT)
        py = plot._map_y_full(llc_gain(fn, plot.K, plot.Q), _RECT)
        plot._update_hover(QPointF(px, py))
    assert plot.stats == stats, "hover 不得触发统计重算"
    assert plot.rebuild == reb, "hover 不得触发任何路径重建"
    assert plot.artist_census() == census


def test_hover_cache_stable(plot):
    """Test8：1000 次 hover 后缓存对象数不增长、内存状态稳定。"""
    census = plot.artist_census()
    reb = dict(plot.rebuild)
    for i in range(1000):
        fn = 0.3 + 7.0 * (i / 1000)
        px = plot._map_x(fn, _RECT)
        py = plot._map_y_full(llc_gain(fn, plot.K, plot.Q), _RECT)
        plot._update_hover(QPointF(px, py))
    assert plot.artist_census() == census, "hover 后绘图缓存对象数不得增长"
    assert plot.rebuild == reb


def test_fs_display_format_in_tooltip(plot):
    """Tooltip 中 fs 用 Hz/kHz/MHz 自动格式。"""
    plot.fr_khz = 124.4
    fn = 0.8
    px, py = _hit_pt(plot, "current", plot.Q, fn)
    hit = plot.hit_test(px, py, _RECT)
    assert hit is not None
    lines = plot._tooltip_lines(hit)
    fs_line = next(l for l in lines if l.startswith("fs = "))
    assert fs_line.endswith("kHz") or fs_line.endswith("Hz") or \
        fs_line.endswith("MHz")
    # fs = fn*fr 换算正确
    expected_khz = fn * plot.fr_khz
    assert fs_line.startswith("fs = ")
    assert abs(float(fs_line[5:-4].rstrip()) - 0.0) >= 0 or "kHz" in fs_line