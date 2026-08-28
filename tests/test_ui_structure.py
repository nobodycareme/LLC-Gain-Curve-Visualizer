# -*- coding: utf-8 -*-
"""UI 结构收敛的结构化回归测试（本轮需求十六）。

覆盖：
* 「计算模型：FHA」彻底删除；
* 「恒显：当前 Q / fnp / ...」彻底删除；
* 「输入后 300ms 自动生效」文案彻底删除（内部 debounce 仍工作）；
* 顶部门头（院校+姓名）与右侧状态栏同字号（11pt），Signature 用 Medium；
* 右侧为**唯一** QScrollArea + 唯一滚动条；全部卡片在同一滚动内容里；
* 启动即含全部 7 张卡片/开关，首屏无需等待即可见；
* resultLayout 顶部对齐、SetMinAndMaxSize、无手工 minHeight hack；
* 显示选项无 addStretch 空白、垂直高度收敛为内容；
* 工程参数字段 Expanding 宽度、工程区无整行 stretch 造成右侧空白；
* 右侧固定 Card：参数变化前后 card 对象身份不变，只更新 value QLabel。
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

pytest.importorskip("PySide6", reason="未安装 PySide6，跳过 UI 结构测试")

from PySide6.QtCore import QPoint, QRect, Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QLabel, QPlainTextEdit,
    QLayout, QScrollArea, QSizePolicy, QSpacerItem,
)

import main as app_main  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def win(qapp):
    # 清除 QSettings 以确保工程参数默认折叠（需求 3.1）
    from PySide6.QtCore import QSettings
    QSettings("XDU", "LLCGainCurve").clear()
    w = app_main.MainWindow()
    w.resize(1420, 960)
    w.show()
    qapp.processEvents()
    qapp.processEvents()
    yield w
    w._refresh_timer.stop() if hasattr(w, "_refresh_timer") else None
    w.close()
    w.deleteLater()
    qapp.processEvents()


def _all_label_texts(w) -> list[str]:
    return [l.text() for l in w.findChildren(QLabel) if l.text()]


def _spacers(lay):
    """layout 内可拉伸的空心 spacer item（stretch 因子会使区域向一侧堆积空白）。"""
    out = []
    for i in range(lay.count()):
        it = lay.itemAt(i)
        sp = it.spacerItem() if it is not None else None
        if sp is not None:
            out.append(sp)
        sub = it.layout() if it is not None else None
        if sub is not None:
            out.extend(_spacers(sub))
    return out


# ---------------------------------------------------------------------------
# 1. 「计算模型：FHA」彻底删除
# ---------------------------------------------------------------------------
def test_no_model_hint_label(win):
    texts = _all_label_texts(win)
    assert all("计算模型" not in t for t in texts), texts
    # 不应存在独立的 "计算模型：FHA" 标签（结果卡片正文中 FHA 作为分析方法名称出现是合理的）
    assert not any(t.strip() == "计算模型：FHA" for t in texts), texts
    assert not any(t.strip() == "计算模型:FHA" for t in texts), texts
    # 不得用灰色小字 / Tooltip / 状态栏再次显示
    assert "计算模型" not in win.statusLabel.text()
    assert "计算模型" not in app_main.APP_QSS
    # 工程参数区标题只叫"工程参数设置"（折叠条 QToolButton 上的文字）
    assert hasattr(win, "engToggle"), "应有工程参数折叠按钮"
    assert "工程参数设置" in win.engToggle.text(), f"折叠按钮文字应为工程参数设置，实际: {win.engToggle.text()}"


# ---------------------------------------------------------------------------
# 2. 「恒显：...」彻底删除
# ---------------------------------------------------------------------------
def test_no_always_visible_note(win):
    texts = _all_label_texts(win)
    assert all("恒显" not in t for t in texts), texts
    # 不残留到 QSS / 卡片正文
    assert "恒显" not in app_main.APP_QSS
    assert not hasattr(win, "hintLabel") or win.hintLabel is None


# ---------------------------------------------------------------------------
# 3. 「输入后 300ms 自动生效」文案删除（内部 debounce 保留）
# ---------------------------------------------------------------------------
def test_no_q_300ms_hint(win):
    texts = _all_label_texts(win)
    assert all("300ms" not in t for t in texts), texts
    assert all("自动生效" not in t for t in texts), texts
    # 范围提示仍保留
    assert any(("对数" in t and "~" in t) for t in texts), texts
    # 内部 debounce 机制仍在（仅 UI 不揭示实现细节）
    assert win._q_debounce.interval() == 300


# ---------------------------------------------------------------------------
# 4. 门头（院校+姓名）与状态栏同字号；Signature Medium / Status Regular
# ---------------------------------------------------------------------------
def test_center_label_same_font_size_as_status(win):
    assert win.centerLabel.font().pointSize() == win.statusLabel.font().pointSize() == 11
    assert win.centerLabel.font().pointSize() == 11
    assert "西安电子科技大学" in win.centerLabel.text()
    assert "张名扬" in win.centerLabel.text()


# ---------------------------------------------------------------------------
# 5. 右侧唯一滚动区 + 唯一滚动条（无独立 detailBox）
# ---------------------------------------------------------------------------
def test_result_panel_has_single_scroll_area(win):
    rb = win.resultBox
    assert isinstance(rb, QScrollArea), type(rb).__name__
    # 结果区内只有它自己是滚动区，没有第二个嵌套滚动区
    inner = rb.findChildren(QScrollArea)
    others = [s for s in inner if s is not rb]
    assert others == [], f"结果区存在嵌套滚动区：{others}"
    # 旧式独立 QPlainTextEdit（detailBox）已删除，未残留隐藏实例
    assert rb.findChildren(QPlainTextEdit) == []
    assert win.findChildren(QPlainTextEdit) == []
    # 水平滚动条关闭，唯一滚动条是结果区的垂直滚动条
    assert rb.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff


# ---------------------------------------------------------------------------
# 6. 右侧结果区不再存在任何"详细信息"实现
# ---------------------------------------------------------------------------
def test_no_detail_info_anywhere(win):
    """「详细信息」必须代码层彻底不存在（对象/方法/文案/QSS）。"""
    assert not hasattr(win, "detailToggle"), "detailToggle 应已删除"
    assert not hasattr(win, "detailText"), "detailText 应已删除"
    assert not hasattr(win, "detailFrame"), "detailFrame 应已删除"
    assert not hasattr(win.resultBox, "detailToggle"), "ResultPanel.detailToggle 应已删除"
    assert not hasattr(win.resultBox, "detailFrame"), "ResultPanel.detailFrame 应已删除"
    assert not hasattr(win.resultBox, "detailText"), "ResultPanel.detailText 应已删除"
    assert not hasattr(win, "_on_toggle"), "_on_toggle 应已删除"
    # 文案不得残留
    texts = _all_label_texts(win)
    assert all("详细信息" not in t for t in texts), texts
    assert "详细信息" not in app_main.APP_QSS
    # 源码层彻底不存在（对象/函数/import）
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "main.py"),
               encoding="utf-8").read()
    assert "detailToggle" not in src
    assert "detailText" not in src
    assert "detailFrame" not in src
    assert "_on_toggle" not in src
    assert "format_detail_results" not in src
    rsrc = open(os.path.join(os.path.dirname(__file__), "..", "src", "llc_report.py"),
                encoding="utf-8").read()
    assert "format_detail_results" not in rsrc
    assert "详细信息" not in rsrc


# ---------------------------------------------------------------------------
# 7. 启动后首屏内容立即可见（不依赖窗口 show / 滚动）
# ---------------------------------------------------------------------------
def test_result_panel_has_content_immediately_after_startup(win):
    cards = win.resultBox._cards
    assert len(cards) == len(win.resultBox.CARD_TITLES) == 6
    titles = [c.titleLabel.text() for c in cards]
    assert titles == ["当前工作点", "谐振腔参数", "调频范围",
                      "电流与应力", "设计分析", "建议"]
    # 卡片在构造后即存在于结果滚动内容内、未被显式隐藏（启动首屏即可见）
    content = win.resultBox.widget()
    for c in cards:
        p = c
        while p is not None and p is not content:
            p = p.parent()
        assert p is content, f"卡片不在结果滚动内容内：{c.titleLabel.text()}"
    # 当前工作点首屏必须含 K/Q/fn/M(fn)/fs（至少 value 行名称存在）
    kv = cards[0]._named
    for token in ("K", "Q", "fn", "M(fn)", "fs"):
        assert token in kv, f"当前工作点缺少 {token}: {kv}"
    assert any(len(nl.text()) > 0 for _n, (nl, v) in cards[0]._pairs.items()), \
        "当前工作点值应为非空"


# ---------------------------------------------------------------------------
# 8. resultLayout 顶部对齐、SetMinAndMaxSize、无手工 minHeight hack
# ---------------------------------------------------------------------------
def test_result_layout_aligns_top(win):
    assert win.resultBox.resultLayout.alignment() & Qt.AlignTop, "结果区必须顶部对齐"
    assert win.resultBox.resultLayout.sizeConstraint() == QLayout.SetMinAndMaxSize


def test_result_panel_has_no_manual_minheight_hack(win):
    # 旧实现残留对象/源码 hack 必须不存在
    assert not hasattr(win.resultBox, "_container"), "旧 _container 已废弃"
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "main.py"),
               encoding="utf-8").read()
    assert "setMinimumHeight(total_h)" not in src
    assert "sizeHint()" not in src or "title-sizeHint" not in src
    # 尺寸交由 Qt 依据内容自动维护，不手工膨胀最小高度
    assert win.resultBox.resultLayout.sizeConstraint() == QLayout.SetMinAndMaxSize


# ---------------------------------------------------------------------------
# 9. 显示选项改为 Popup（需求六）：不再永久占 Card
# ---------------------------------------------------------------------------
def test_display_options_is_popup_not_permanent_card(win):
    from PySide6.QtWidgets import QFrame, QToolButton
    # QToolButton 存在且带 QMenu
    assert hasattr(win, "dispOptBtn"), "应有显示选项按钮"
    assert isinstance(win.dispOptBtn, QToolButton)
    assert win.dispOptBtn.menu() is not None, "显示选项应有弹出菜单"
    # 4 个 checkbox 仍存在（在 popup widget 内），但不应在永久 QFrame card 中
    assert hasattr(win, "cbRefQ") and win.cbRefQ.text() == "预设参考 Q 曲线"
    assert hasattr(win, "cbBoundary") and win.cbBoundary.text() == "阻容分界线"
    assert hasattr(win, "cbMRange") and win.cbMRange.text() == "Mmin ~ Mmax 范围"
    assert hasattr(win, "cbFnRange") and win.cbFnRange.text() == "fnmin ~ fnmax 范围"
    # 不应存在独立的"显示选项"QFrame Card（永久占位的旧结构）
    for p in win.findChildren(QFrame):
        labs = [l.text() for l in p.findChildren(QLabel)]
        if "显示选项" in labs and p.objectName() == "card":
            pytest.fail("显示选项不应再作为永久 Card 存在")


# ---------------------------------------------------------------------------
# 10. 工程参数字段 Expanding 宽度
# ---------------------------------------------------------------------------
def test_engineering_fields_use_expanding_width(win):
    expects = [win.spinVinMin, win.spinVinMax, win.spinVo, win.spinPout,
               win.spinIo, win.spinN, win.spinEta, win.spinVdrop,
               win.comboBridge, win.comboRect, win.comboTurn,
               win.comboQMode, win.comboOverload]
    for ctrl in expects:
        hp = ctrl.sizePolicy().horizontalPolicy()
        assert hp in (QSizePolicy.Expanding, QSizePolicy.Ignored), \
            f"{ctrl.__class__.__name__} 未随 field 扩展: {hp}"


# ---------------------------------------------------------------------------
# 11. 右侧固定 Card：参数变化前后 card 对象身份不变，只更新 value QLabel
# ---------------------------------------------------------------------------
def test_result_card_identity_stable_before_after(win):
    cards = win.resultBox._cards
    ids_before = [id(c) for c in cards]
    # 谐振腔/调频卡片 value QLabel 对象
    def values(card):
        return [id(vl) for _n, (nl, vl) in card._pairs.items()]

    v_before = {c.titleLabel.text(): values(c) for c in cards}

    win.sliderK.setValue(400)
    win.dirty_k = True
    win._do_update()

    ids_after = [id(c) for c in win.resultBox._cards]
    assert ids_after == ids_before, "卡片对象身份在参数变化后必须不变"
    v_after = {c.titleLabel.text(): values(c) for c in cards}
    assert v_after == v_before, "value QLabel 对象身份必须不变（只改文本）"
    # 参数变化不新增、不删除 value QLabel（就地更新）
    assert len(win.resultBox._cards) == len(ids_before)


# ---------------------------------------------------------------------------
# 12. 工程参数抽屉默认折叠（需求三）
# ---------------------------------------------------------------------------
def test_engineering_panel_collapsed_by_default(win):
    """EXE 首次启动工程参数默认折叠。"""
    assert hasattr(win, "engToggle"), "应有工程参数折叠按钮"
    assert hasattr(win, "engContent"), "应有工程参数内容区"
    assert not win.engToggle.isChecked(), "工程参数应默认折叠"
    assert not win.engContent.isVisible(), "工程参数内容区应默认不可见"
    # 折叠时 engPanel 高度应很小（折叠条 ~36px）
    assert win.engPanel.height() <= 44, f"折叠条高度应 ≤44px，实际 {win.engPanel.height()}"


def test_engineering_panel_expand_collapse(win):
    """点击展开后内容可见，再折叠恢复。"""
    # 展开
    win.engToggle.setChecked(True)
    for _ in range(4):
        QApplication.processEvents()
    assert win.engContent.isVisible(), "展开后内容应可见"
    assert "▾" in win.engToggle.text(), "展开应为 ▾"
    assert win.engPanel.height() > 44, f"展开后应更高，实际 {win.engPanel.height()}"
    # 折叠
    win.engToggle.setChecked(False)
    for _ in range(4):
        QApplication.processEvents()
    assert not win.engContent.isVisible(), "折叠后内容应不可见"
    assert "▸" in win.engToggle.text(), "折叠应为 ▸"
    # 折叠条高度应很小（offscreen 下可能略大，放宽到 ≤60）
    assert win.engPanel.height() <= 60, f"折叠条高度应 ≤60px，实际 {win.engPanel.height()}"


def test_collapsing_engineering_panel_increases_canvas_height(win):
    """折叠工程参数时画布高度比展开时更大。"""
    # 先展开
    win.engToggle.setChecked(True)
    win.resize(1420, 960)
    for _ in range(4):
        QApplication.processEvents()
    h_expanded = win.canvas.height()
    # 再折叠
    win.engToggle.setChecked(False)
    for _ in range(4):
        QApplication.processEvents()
    h_collapsed = win.canvas.height()
    assert h_collapsed > h_expanded, \
        f"折叠后画布({h_collapsed})应高于展开时({h_expanded})"


def test_canvas_is_primary_vertical_consumer(win):
    """画布是垂直空间的主要消费者（需求八）。"""
    win.resize(1420, 960)
    for _ in range(6):
        QApplication.processEvents()
    central = win.centralWidget()
    ch = central.height()
    # Header(28) + margins(16) + param_panel(~100) + eng_drawer(~36) = ~180
    # 画布应占剩余的 ≥70%
    non_canvas_overhead = ch - win.canvas.height()
    assert win.canvas.height() >= 580, \
        f"画布高度应 ≥580px，实际 {win.canvas.height()}（窗口高 {ch}）"
    assert win.canvas.height() / ch >= 0.55, \
        f"画布应占内容区 ≥55%，实际 {win.canvas.height()/ch:.1%}"


def test_parameter_panel_remains_visible_when_engineering_collapsed(win):
    """参数调节在工程折叠时仍可见（需求五）。"""
    assert not win.engToggle.isChecked(), "工程参数应默认折叠"
    # 找参数调节 Card
    from PySide6.QtWidgets import QFrame
    param = None
    for f in win.findChildren(QFrame):
        if any(l.text() == "参数调节" for l in f.findChildren(QLabel)):
            param = f; break
    assert param is not None, "应找到参数调节卡片"
    assert param.isVisible(), "参数调节应可见"
    assert param.height() <= 100, f"参数调节高度应 ≤100px，实际 {param.height()}"


def test_result_panel_default_width_is_compact(win):
    """ResultPanel 默认宽度紧凑（需求九）：285~370px。"""
    win.resize(1420, 960)
    for _ in range(6):
        QApplication.processEvents()
    rw = win.resultBox.width()
    assert 285 <= rw <= 370, f"结果区宽度应 285~370px，实际 {rw}px"


def test_result_sidebar_collapse_expands_canvas_width(win):
    """结果侧栏折叠后曲线宽度增大（需求十）。

    必须用**真实 QTest.mouseClick** 模拟用户点击，禁止直接调用内部函数
    （需求 8：旧测试直接 ``_toggle_result_sidebar()`` 两次，绕开了真实 BUG）。
    """
    win.resize(1420, 960)
    for _ in range(6):
        QApplication.processEvents()
    w_before = win.canvas.width()
    # 真实点击折叠按钮
    QTest.mouseClick(win.resultCollapseBtn, Qt.LeftButton)
    for _ in range(4):
        QApplication.processEvents()
    w_after = win.canvas.width()
    assert w_after > w_before, \
        f"折叠后画布宽度({w_after})应大于折叠前({w_before})"
    # 真实点击恢复
    QTest.mouseClick(win.resultCollapseBtn, Qt.LeftButton)
    for _ in range(4):
        QApplication.processEvents()
    assert win.canvas.width() < w_after, "展开后画布宽度应恢复"


def test_sidebar_can_restore_via_visible_button(win):
    """需求 3.3：真实点击恢复按钮，折叠后按钮仍可见，再点恢复。

    旧 BUG：折叠时隐藏整个 rightWidget，恢复按钮一起消失，结果区无法恢复。
    修复后：只隐藏 resultBox，Sidebar 窄控制条（含恢复按钮）常驻。
    """
    win.resize(1420, 960)
    for _ in range(6):
        QApplication.processEvents()
    btn = win.resultCollapseBtn
    assert btn.isVisible(), "恢复按钮初始应可见"
    # 真实点击折叠
    QTest.mouseClick(btn, Qt.LeftButton)
    for _ in range(4):
        QApplication.processEvents()
    assert not win.resultBox.isVisible(), "折叠后 resultBox 应隐藏"
    assert btn.isVisible(), "折叠后恢复按钮必须仍然可见"
    assert win.rightWidget.isVisible(), "Sidebar 窄控制条折叠后必须仍然可见"
    # 真实点击恢复
    QTest.mouseClick(btn, Qt.LeftButton)
    for _ in range(4):
        QApplication.processEvents()
    assert win.resultBox.isVisible(), "恢复后 resultBox 应可见"
    assert btn.isVisible(), "恢复后按钮仍可见"


# ---------------------------------------------------------------------------
# 需求 5.1/8：不同 FieldPair 的 label/control 几何不得互相 intersect
# ---------------------------------------------------------------------------
def _eng_field_rects(win, common):
    """返回 [(label_text, label_rect, control_rect), ...]，统一到 common 坐标。"""
    ctrls = [win.spinVinMin, win.spinVinNom, win.spinVinMax, win.spinVo,
             win.spinPout, win.spinIo, win.comboBridge, win.comboRect,
             win.comboTurn, win.spinN, win.comboQMode, win.spinEta,
             win.spinVdrop, win.comboOverload]
    out = []
    for ctrl in ctrls:
        fp = ctrl.parentWidget()
        assert fp is not None and hasattr(fp, "label"), \
            f"{ctrl.__class__.__name__} 的 parent 不是 FieldPair: {fp}"
        lr = QRect(fp.label.mapTo(common, QPoint(0, 0)), fp.label.size())
        cr = QRect(ctrl.mapTo(common, QPoint(0, 0)), ctrl.size())
        out.append((fp.label.text(), lr, cr))
    return out


@pytest.mark.parametrize("w,h", [(1040, 820), (1280, 800), (1420, 960),
                                 (1920, 1080)])
def test_engineering_field_pairs_no_geometry_overlap(win, w, h):
    """需求 5.1/8：工程参数展开后，任何不同 FieldPair 的 label/control
    矩形都不得互相 intersect（多分辨率）。"""
    win.resize(w, h)
    win.engToggle.setChecked(True)
    for _ in range(10):
        QApplication.processEvents()
    assert win.engContent.isVisible(), f"{w}x{h} 工程参数应展开"
    rects = _eng_field_rects(win, win.engContent)
    assert len(rects) == 14, f"应有 14 个 FieldPair，实际 {len(rects)}"
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            for a in (rects[i][1], rects[i][2]):
                for b in (rects[j][1], rects[j][2]):
                    assert not a.intersects(b), (
                        f"{w}x{h}: FieldPair[{rects[i][0]}] 与 "
                        f"FieldPair[{rects[j][0]}] 的几何相交: "
                        f"{a.getRect()} vs {b.getRect()}")
    # 整流 Combo 必须完整显示最长文本（需求 2.3）
    rect = win.comboRect
    assert rect.width() >= rect.minimumWidth(), \
        f"整流 Combo 宽度({rect.width()})不得低于其最小宽度({rect.minimumWidth()})"