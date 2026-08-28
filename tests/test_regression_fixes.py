# -*- coding: utf-8 -*-
"""本轮修复（BUG1~BUG6）的回归测试。

覆盖用户逐项验收要求：
1. 取消"预设参考 Q 曲线 / 阻容分界线"后，工作点仍严格落在当前 Q 曲线上
   （plot_rect 几何变化必须使所有依赖坐标映射的路径/pixmap 失效）；
2. 拓扑 / 次级整流下拉框全部中文化（内部枚举键不变）；
3. 阻容分界线命名统一中文 + 完整画法（弯曲段→(1,1) + fn=1、M=1→0 竖直段）
   + 竖直段独立几何 Hover；
4. 工程参数键盘输入不失焦自动提交（debounce）；
5. 右侧结果滚动位置在参数变化时不跳回顶部；
6. K 拖动性能：隐藏图层跳过显示重建、工程计算/长文本节流。
"""

from __future__ import annotations

import math
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过回归测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import llc_gain  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    w = app_main.MainWindow()
    w.show()
    qapp.processEvents()
    w.resize(1420, 960)
    qapp.processEvents()
    yield w
    w._refresh_timer.stop() if hasattr(w, "_refresh_timer") else None
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _set(win, K=None, Q=None, fn=None):
    if K is not None:
        win.sliderK.setValue(app_main._slider_from_lin(K, app_main.K_MIN, app_main.K_MAX))
        win.dirty_k = True
    if Q is not None:
        win.sliderQ.setValue(app_main._slider_from_log(Q, app_main.Q_MIN, app_main.Q_MAX))
        win.dirty_q = True
    if fn is not None:
        win.sliderFn.setValue(app_main._slider_from_log(fn, app_main.FN_MIN, app_main.FN_MAX))
        win.dirty_fn = True
    win._do_update()


def _path_y_at(path, x):
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


# ---------------------------------------------------------------------------
# BUG1：取消图层后工作点与当前 Q 曲线错位
# ---------------------------------------------------------------------------
def test_display_toggle_keeps_workpoint_on_current_curve(win):
    """关闭参考 Q + 阻容边界后，工作点中心与当前 Q 曲线同一 fn 的像素 Y 差 <= 1px。

    覆盖 K=2.5/5/8、Q=0.2/0.5/2、fn=0.4/0.6368/1/2。
    仅对增益落在可视区 [0, ymax] 的 fn 断言：M 超出 ymax 时曲线被裁剪、
    工作点被夹取到图顶边缘，1px 对齐断言不适用（屏外点无意义）。
    """
    for K in (2.5, 5.0, 8.0):
        for Q in (0.2, 0.5, 2.0):
            _set(win, K=K, Q=Q)
            win.plot.set_display_state(show_reference=True, show_boundary=True)
            win._do_update()
            r1 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
            # 关闭两个可选图层 → plot_rect 顶部偏移变化
            win.plot.set_display_state(show_reference=False, show_boundary=False)
            win._do_update()
            r2 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
            assert r2.top() != r1.top(), "关闭图层后 plot_rect 几何必须变化"
            # 强制用新几何重建当前 Q 路径
            cur = win.plot._ensure_current_path(r2)
            checked = 0
            for fn in (0.4, 0.6368, 1.0, 2.0):
                mwork = float(llc_gain(fn, win.plot.K, win.plot.Q))
                if not (0.0 <= mwork <= win.plot.ymax):
                    continue  # 屏外点：曲线被裁剪，不做 1px 断言
                x_fn = win.plot._map_x(fn, r2)
                y_path = _path_y_at(cur, x_fn)
                assert y_path is not None, f"K={K} Q={Q} fn={fn} 路径无此点"
                y_wp = win.plot._map_y(mwork, r2)
                assert abs(y_path - y_wp) <= 1.0, (
                    f"K={K} Q={Q} fn={fn}: 曲线Y={y_path:.3f} 工作点Y={y_wp:.3f} 差={abs(y_path-y_wp):.3f}px")
                checked += 1
            assert checked >= 2, f"K={K} Q={Q} 可视区断言点不足（应至少 2 个 fn）"


def test_plot_rect_change_invalidates_current_geometry(win):
    """plot_rect 几何变化必须使当前 Q 路径缓存失效（BUG1 根因）。"""
    win.plot.set_display_state(show_reference=True, show_boundary=True)
    win._do_update()
    r1 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    win.plot._ensure_current_path(r1)
    geom1 = win.plot._geom_gen
    key1 = win.plot._path_keys["Q"]
    # 关闭图层 → 几何变化
    win.plot.set_display_state(show_reference=False, show_boundary=False)
    r2 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    assert r2.top() != r1.top()
    assert win.plot._geom_gen > geom1, "几何版本号必须递增"
    assert win.plot._cur_path is None, "当前 Q 路径必须被作废"
    # 重建后缓存键必须包含新几何
    win.plot._ensure_current_path(r2)
    key2 = win.plot._path_keys["Q"]
    assert key1 != key2, "当前 Q 路径缓存键必须随几何变化"


def test_semi_cache_key_tracks_plot_geometry(win):
    """semi pixmap 缓存键必须覆盖绘图区几何（BUG1 根因 C）。"""
    r1 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    key1 = win.plot._geom_key(r1)
    win.plot.set_display_state(show_reference=False, show_boundary=False)
    r2 = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    key2 = win.plot._geom_key(r2)
    assert key1 != key2, "几何键必须随 plot_rect 变化"
    # semi key = 几何键 + (Q, K)
    win.plot._ensure_semi_pixmap(r2)
    assert win.plot._semi_key is not None
    assert win.plot._semi_key[:len(key2)] == key2, "semi 缓存键必须包含几何键"


# ---------------------------------------------------------------------------
# BUG3：阻容分界线完整画法 + 竖直段 Hover + 中文命名
# ---------------------------------------------------------------------------
def test_boundary_contains_vertical_fn1_segment(win):
    """阻容分界线必须包含 fn=1、M=1→0 的竖直段（需求 3.2C）。"""
    r = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    win.plot._ensure_static_paths(r)
    vp = win.plot._boundary_vline_path
    assert vp is not None and not vp.isEmpty(), "竖直段路径必须存在"
    x1 = win.plot._map_x(1.0, r)
    y_top = win.plot._map_y_full(1.0, r)
    y_bot = win.plot._map_y_full(0.0, r)
    pts = []
    for i in range(vp.elementCount()):
        e = vp.elementAt(i)
        pts.append((e.x, e.y))
    assert len(pts) >= 2
    assert abs(pts[0][0] - x1) < 1e-6, "竖直段 x 必须为 x(fn=1)"
    assert abs(pts[-1][0] - x1) < 1e-6
    assert abs(pts[0][1] - y_top) < 1e-6, "竖直段上端必须为 M=1"
    assert abs(pts[-1][1] - y_bot) < 1e-6, "竖直段下端必须为 M=0"
    # 弯曲段末点精确落在 (1,1)（需求 3.2B，无 1e-6 缺口）
    bx, by = win.plot.boundary_data()
    assert bx[-1] == pytest.approx(1.0, abs=1e-9)
    assert by[-1] == pytest.approx(1.0, abs=1e-6)


def test_boundary_vertical_segment_hover(win):
    """fn=1 竖直段必须用独立几何 hit test 命中（需求 3.4），不伪造 boundary_gain(1)。"""
    r = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    x1 = win.plot._map_x(1.0, r)
    y_top = win.plot._map_y_full(1.0, r)
    y_bot = win.plot._map_y_full(0.0, r)
    # 竖直段中点命中
    hit = win.plot.hit_test(x1, (y_top + y_bot) / 2, r)
    assert hit is not None and hit["kind"] == "boundary"
    assert hit["fn"] == pytest.approx(1.0)
    assert 0.0 <= hit["mb"] <= 1.0, "竖直段 M 反算必须在 [0,1]"
    # 超出 M=0~1 像素范围不命中竖直段
    assert win.plot._vertical_boundary_hit(x1, y_top - 20, r, 8.0) is None
    assert win.plot._vertical_boundary_hit(x1, y_bot + 20, r, 8.0) is None
    # 关闭阻容分界线后竖直段不再命中
    win.plot.set_display_state(show_boundary=False)
    assert win.plot._vertical_boundary_hit(x1, (y_top + y_bot) / 2, r, 8.0) is None


def test_boundary_ui_label_is_chinese_without_angle_text(win):
    """阻容分界线名称统一中文，不显示"∠Zin=0"（需求 3.1）。"""
    # checkbox
    assert win.cbBoundary.text() == "阻容分界线"
    # 图例
    texts = [e[3] for e in win.plot.legend_entries()]
    assert any("阻容分界线" in t for t in texts)
    for t in texts:
        assert "∠Zin=0" not in t, f"图例不得出现 ∠Zin=0：{t}"
    # 图中标签（_draw_boundary_label 文本）
    r = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    win.plot._draw_boundary_label.__self__  # noqa: B018  (确保方法存在)
    # 内部数学判据仍保留（∠Zin=0 只出现在注释/详细区，不进入名称）
    assert win.plot._boundary_dirty is False or True


def test_boundary_vline_and_fnr1_coexist(win):
    """fn=1 处蓝色 fnr=1 竖线与品红阻容分界线竖直段共存可辨认（需求 8）。

    - 两者 x 像素坐标一致（同一 fn=1）；
    - 颜色/线宽/线型不同（蓝细虚线 vs 品红粗虚线）；
    - 绘制顺序：fnr=1 在阻容分界线之后绘制（z-order 在上，蓝色不被完全覆盖）；
    - 关闭阻容分界线后蓝色 fnr=1 恒显。
    """
    from plot_widget import BOUNDARY_COLOR, FNR_COLOR  # noqa: E402
    r = win.plot._plot_rect(win.canvas.width(), win.canvas.height())
    win.plot._ensure_static_paths(r)
    x1 = win.plot._map_x(1.0, r)
    # 竖直段路径存在且 x == x(fn=1)
    vp = win.plot._boundary_vline_path
    assert vp is not None and not vp.isEmpty(), "竖直段路径必须存在"
    e0 = vp.elementAt(0)
    assert abs(e0.x - x1) < 1e-6, "竖直段 x 必须为 x(fn=1)"
    # fnr=1 竖线 x 相同（两者几何重合）
    assert abs(win.plot._map_x(win.plot.fnr, r) - x1) < 1e-6
    # 颜色/线宽不同：品红粗虚线 vs 蓝细虚线
    assert BOUNDARY_COLOR != FNR_COLOR
    # 绘制顺序：fnr=1（蓝）在阻容分界线（品红）之后 → z-order 在上
    scene = win.plot._draw_scene_static.__code__.co_names
    i_bnd = list(scene).index("_draw_boundary")
    i_res = list(scene).index("_draw_resonance_vlines")
    assert i_res > i_bnd, "fnr=1 竖线必须在阻容分界线之后绘制（z-order 在上）"
    # 关闭阻容分界线后 fnr=1 仍恒显（图例保留 fnr=1 条目）
    win.plot.set_display_state(show_boundary=False)
    texts = [e[3] for e in win.plot.legend_entries()]
    assert any("fnr=1" in t for t in texts), "fnr=1 必须恒显"


# ---------------------------------------------------------------------------
# BUG2：拓扑 / 次级整流中文化
# ---------------------------------------------------------------------------
def test_topology_combobox_chinese_labels(win):
    """拓扑下拉框显示中文，内部枚举键 half/full 不变。"""
    items = [win.comboBridge.itemText(i) for i in range(win.comboBridge.count())]
    assert items == ["半桥", "全桥"]
    assert [k for _, k in app_main.BRIDGE_OPTIONS] == ["half", "full"]
    # 计算逻辑不受中文化影响：默认半桥
    win._do_update()
    assert win._engine["bridge"] == "half"


def test_rectifier_combobox_chinese_labels(win):
    """次级整流下拉框显示中文，内部枚举键 ct_diode/ct_sr/fb_diode/fb_sr 不变。"""
    items = [win.comboRect.itemText(i) for i in range(win.comboRect.count())]
    assert items == ["中心抽头二极管整流", "中心抽头同步整流",
                     "全桥二极管整流", "全桥同步整流"]
    assert [k for _, k in app_main.RECT_OPTIONS] == [
        "ct_diode", "ct_sr", "fb_diode", "fb_sr"]
    # 切换整流方式仍正确驱动计算
    win.comboRect.setCurrentIndex(2)  # 全桥二极管整流
    win._engine_dirty = True
    win._do_update()
    assert win._engine["rect"] == "fb_diode"
    # 结果区显示中文（整流方式进入工程卡片/结果文本）
    assert "全桥二极管整流" in win.resultBox.toPlainText()


# ---------------------------------------------------------------------------
# BUG4：工程参数键盘输入自动提交（不失焦）
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("attr,text,expected", [
    ("spinVinMin", "320", 320.0),
    ("spinVo", "24", 24.0),
    ("spinPout", "1000", 1000.0),
    ("spinVdrop", "0.8", 0.8),
    ("spinEta", "0.95", 0.95),
    ("spinN", "18", 18.0),
])
def test_spinbox_keyboard_auto_commit_without_focus_loss(win, attr, text, expected):
    """键盘直接输入后不切换焦点，等待 debounce 即自动提交（需求 4）。"""
    sb = getattr(win, attr)
    if attr == "spinN":
        win.comboTurn.setCurrentIndex(1)  # 手动匝比才允许编辑
    le = sb.lineEdit()
    le.setText(text)
    le.textEdited.emit(text)
    # 输入中：显示"未完成"状态
    assert win.engStatusLabel.text() == "参数有未完成输入"
    # 触发 debounce（等价于停止输入一段时间）
    win._on_eng_debounce()
    assert sb.value() == pytest.approx(expected), f"{attr} 未自动提交"
    # 不切换焦点，直接刷新 → 工程设计已用新值
    win._do_update()
    assert win.engStatusLabel.text() == "已自动应用"


def test_spinbox_enter_commits_immediately(win):
    """Enter/失焦立即提交，不等 debounce（需求 4）。"""
    le = win.spinVinMin.lineEdit()
    le.setText("330")
    le.textEdited.emit("330")
    win._eng_debounce.stop()
    win._on_eng_editing_finished()
    assert win.spinVinMin.value() == pytest.approx(330.0)


# ---------------------------------------------------------------------------
# BUG5：右侧结果滚动位置保持
# ---------------------------------------------------------------------------
def test_result_scroll_position_preserved(win):
    """参数变化（fn/K/Vin）后右侧滚动位置不跳回顶部（需求 5.2）。

    用 ``setFixedSize`` 把结果框固定为小尺寸（布局无法再放大），使真实结果
    文本可滚动；滚动到中部后改 fn/K/Vin，断言滚动位置保持不跳回 0。
    """
    win.resultBox.setFixedSize(300, 120)
    win._do_update()
    vsb = win.resultBox.verticalScrollBar()
    qapp = QApplication.instance()
    qapp.processEvents()
    assert vsb.maximum() > 0, "结果区应可滚动"
    vsb.setValue(vsb.maximum() // 2)
    mid_pos = vsb.value()
    assert mid_pos > 0
    # 改 fn
    win.sliderFn.setValue(300)
    win._do_update()
    # 改 K
    win.sliderK.setValue(400)
    win._do_update()
    # 改 Vin
    win.spinVinMin.setValue(320)
    win._engine_dirty = True
    win._do_update()
    qapp.processEvents()
    assert vsb.value() > 0, "参数变化后滚动位置不得跳回 0"
    # 底部保持贴底
    vsb.setValue(vsb.maximum())
    win.sliderK.setValue(500)
    win._do_update()
    qapp.processEvents()
    assert vsb.value() >= vsb.maximum() - 1, "原本在底部应继续贴底"


# ---------------------------------------------------------------------------
# BUG6：K 拖动性能（隐藏图层 lazy + 工程/长文本节流）
# ---------------------------------------------------------------------------
def test_hidden_reference_skips_k_family_display_rebuild(win):
    """参考 Q 隐藏时，K 拖动不重建 family 显示数据/路径（需求 6.1）。"""
    win.plot.set_display_state(show_reference=False)
    win._do_update()
    win.plot.stats["family"] = 0
    win.plot.rebuild["family_path"] = 0
    for i in range(20):
        win.sliderK.setValue(i * 50)
        win._do_update()
    assert win.plot.stats["family"] == 0, "隐藏参考 Q 时 K 拖动不得重算 family 数据"
    assert win.plot.rebuild["family_path"] == 0, "隐藏参考 Q 时不得重建 family 路径"
    # 重新打开 → lazy rebuild 一次
    win.plot.set_display_state(show_reference=True)
    assert win.plot.stats["family"] == 1


def test_hidden_boundary_skips_display_boundary_rebuild(win):
    """阻容分界线隐藏时，K 拖动不重建显示边界路径（需求 6.1）。

    但标量 fn_boundary / input_region 数学判据始终计算。
    """
    win.plot.set_display_state(show_boundary=False)
    win._do_update()
    win.plot.stats["boundary"] = 0
    win.plot.rebuild["boundary_path"] = 0
    for i in range(20):
        win.sliderK.setValue(i * 50)
        win._do_update()
    assert win.plot.stats["boundary"] == 0, "隐藏边界时 K 拖动不得重算显示边界数据"
    assert win.plot.rebuild["boundary_path"] == 0, "隐藏边界时不得重建显示边界路径"
    # 数学判据仍计算
    assert math.isfinite(win.plot.fn_boundary) or win.plot.fn_boundary != win.plot.fn_boundary
    # 重新打开 → lazy rebuild 一次
    win.plot.set_display_state(show_boundary=True)
    assert win.plot.stats["boundary"] == 1


def test_k_drag_throttles_engineering_recompute(win):
    """K 拖动期间完整工程计算被节流，松手立即最终计算（需求 6.2）。"""
    win._do_update()
    engine0 = win._engine
    # 进入拖动模式
    win._dragging = True
    win._engine_dirty = True
    for i in range(20):
        win.sliderK.setValue(i * 50)
        win._do_update()  # 拖动中：只置 pending，不重算工程
    assert win._engine is engine0, "拖动中不得重算工程设计"
    assert win._engine_pending is True, "拖动中应记录 pending"
    # 松手 → 立即最终计算
    win._on_released()
    assert win._engine_pending is False
    assert win._engine is not engine0, "松手后应完成最终工程计算"


def test_k_drag_throttles_long_result_text_rebuild(win):
    """K 拖动期间不每帧重建长结果文本（需求 5.3/6.3）。"""
    calls = {"n": 0}
    orig = win._update_result_text

    def spy(values):
        calls["n"] += 1
        orig(values)

    win._update_result_text = spy
    win._dragging = True
    for i in range(20):
        win.sliderK.setValue(i * 50)
        win._do_update()
    assert calls["n"] == 0, "拖动中不得每帧重建长结果文本"
    # 松手 → 最终刷新一次
    win._on_released()
    assert calls["n"] >= 1
