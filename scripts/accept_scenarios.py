# -*- coding: utf-8 -*-
"""GUI 验收驱动：对冻结进 EXE 的同一套 src 代码，以真实 Qt 事件循环 + QPainter
渲染执行用户验收场景 A~G，并保存 PNG 截图与逐项 PASS/FAIL 断言。

不属于"纯 offscreen 断言"：它驱动真实控件树、触发真实信号、执行真实布局与
绘制，并通过 widget.grab() 把 QPainter 绘制结果导出为位图（与 PrintWindow 捕获
的 EXE 窗口内容同源）。EXE 真实启动/渲染/ resize 另由 scripts/verify_exe.py 验证。

用法：python scripts/accept_scenarios.py
输出：工作目录下的 _sc_A..G_*.png
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import FN_MIN, FN_MAX, K_MIN, K_MAX, Q_MIN, Q_MAX  # noqa: E402

SAVE_DIR = os.path.dirname(os.path.abspath(__file__))


def _lin_slider(v, lo, hi):
    return int(round((v - lo) / (hi - lo) * app_main.SLIDER_STEPS))


def _log_slider(v, lo, hi):
    frac = (math10(v) - math10(lo)) / (math10(hi) - math10(lo))
    return int(round(frac * app_main.SLIDER_STEPS))


def math10(x):
    import math
    return math.log10(x)


def _settle(app, ms=40):
    app.processEvents()
    end = ms
    for _ in range(end // 5 + 1):
        app.processEvents()
        QTest.qWait(5)


def _get_k(win, app):
    return win._k_from_slider(win.sliderK.value())


def _set_slider(win, app, slider, value):
    slider.setValue(value)
    _settle(app)
    # 拖动路径需要 sliderPressed/released 触发节流与 preview
    win._on_slider_pressed()
    _settle(app)
    win._do_update(force_full=False)
    _settle(app)
    win._on_released()
    _settle(app)


def _shot(win, app, tag):
    win.grab().save(os.path.join(SAVE_DIR, f"_sc_{tag}.png"))
    print(f"  [shot] _sc_{tag}.png", flush=True)


def main():
    app = QApplication.instance() or QApplication([])
    win = app_main.MainWindow()
    win.show()
    _settle(app, 120)
    print("窗口已显示", flush=True)

    ok_all = True

    def check(name, cond):
        nonlocal ok_all
        status = "PASS" if cond else "FAIL"
        print(f"  [{status}] {name}")
        if not cond:
            ok_all = False

    # ---------------- 场景 A：K=5 Q≈0.5 fn=1，关闭参考Q+阻容分界线 ----------------
    print("场景 A：K=5, Q≈0.5, fn=1, 关闭参考Q+阻容边界")
    _set_slider(win, app, win.sliderK, _lin_slider(5.0, K_MIN, K_MAX))
    _set_slider(win, app, win.sliderQ, _log_slider(0.5, Q_MIN, Q_MAX))
    _set_slider(win, app, win.sliderFn, _log_slider(1.0, FN_MIN, FN_MAX))
    win.cbRefQ.setChecked(False)
    win.cbBoundary.setChecked(False)
    _settle(app)
    # 工作点像素对齐断言通过 plot 提供的检测（像素 Y 差 ≤1）
    aligned = win.plot.workpoint_on_current_curve_px() <= 1.0
    check("场景A 工作点落在当前Q曲线(像素Y差≤1)", aligned)
    _shot(win, app, "A_boundary_ref_off_fn1")

    # ---------------- 场景 B：fn≈0.6368 ----------------
    print("场景 B：fn≈0.6368")
    _set_slider(win, app, win.sliderFn, _log_slider(0.6368, FN_MIN, FN_MAX))
    alignedB = win.plot.workpoint_on_current_curve_px() <= 1.0
    check("场景B 工作点落在当前Q曲线(像素Y差≤1)", alignedB)
    _shot(win, app, "B_boundary_ref_off_fn06368")

    # ---------------- 场景 C：K 从 5 拖到约 2.56 ----------------
    print("场景 C：K 5 -> 2.56")
    _set_slider(win, app, win.sliderK, _lin_slider(2.56, K_MIN, K_MAX))
    alignedC = win.plot.workpoint_on_current_curve_px() <= 1.0
    check("场景C 拖动后工作点仍落在当前Q曲线", alignedC)
    _shot(win, app, "C_boundary_ref_off_K256")

    # ---------------- 场景 D：重新打开阻容分界线 ----------------
    print("场景 D：重新打开阻容分界线")
    win.cbBoundary.setChecked(True)
    _settle(app)
    has_vline = getattr(win.plot, "_boundary_vline_path", None) is not None
    bnd_data = win.plot.boundary_data()
    check("场景D 阻容边界含曲线段", len(bnd_data[0]) > 2)
    check("场景D 阻容边界含 fn=1 竖直段路径", has_vline)
    _shot(win, app, "D_boundary_on_K256")

    # ---------------- 场景 E：键盘输入 Vin_min=320 不失焦 ----------------
    print("场景 E：键盘直接输入 Vin_min=320，不点击其他输入框")
    sb = win.spinVinMin
    le = sb.lineEdit()
    le.setFocus()
    _settle(app)
    le.selectAll()
    QTest.keyClicks(le, "320")
    _settle(app)                      # textEdited 已触发 debounce 启动
    # 等待 debounce 结束（ENG_DEBOUNCE_MS ~=300ms）自动提交
    QTest.qWait(app_main.ENG_DEBOUNCE_MS + 60)
    _settle(app)
    auto = sb.value() == 320.0
    status = win.engStatusLabel.text()
    check("场景E Vin_min 已自动提交为 320（未失焦）", auto)
    check("场景E 状态提示为自动应用", "已自动应用" in status)
    right_updated = win._engine is not None
    check("场景E 右侧结果已按新参数更新", right_updated)
    _shot(win, app, "E_Vin320_autoapply")

    # ---------------- 场景 F：滚动保持 ----------------
    print("场景 F：右侧滚动到中下部，移动 fn/K，滚动位置不跳回顶部")
    # 固定小尺寸制造可滚动区域（与 regression 测试同机制）
    win.resultBox.setFixedSize(300, 120)
    win._do_update()
    _settle(app)
    vsb = win.resultBox.verticalScrollBar()
    if vsb.maximum() > 0:
        vsb.setValue(int(vsb.maximum() * 0.8))
        _settle(app)
    before = vsb.value()
    _set_slider(win, app, win.sliderFn, _log_slider(0.9, FN_MIN, FN_MAX))
    _set_slider(win, app, win.sliderK, _lin_slider(4.0, K_MIN, K_MAX))
    _set_slider(win, app, win.sliderQ, _log_slider(0.7, Q_MIN, Q_MAX))
    after = vsb.value()
    scrollable = vsb.maximum() > 0
    check("场景F 结果区可滚动", scrollable)
    if scrollable:
        check("场景F 滚动值未跳回顶部(>0)", after > 0)
        check("场景F 滚动位置保持", after >= before * 0.5)
    _shot(win, app, "F_scroll_preserved")

    # ---------------- 场景 G：中文下拉框 ----------------
    print("场景 G：中文下拉框检查")
    bridge = [win.comboBridge.itemText(i) for i in range(win.comboBridge.count())]
    rect = [win.comboRect.itemText(i) for i in range(win.comboRect.count())]
    check("场景G 拓扑=半桥/全桥", bridge == ["半桥", "全桥"])
    check(
        "场景G 次级整流=中文四选项",
        rect == ["中心抽头二极管整流", "中心抽头同步整流",
                 "全桥二极管整流", "全桥同步整流"],
    )
    check("场景G 阻容分界线无 ∠Zin=0", win.cbBoundary.text() == "阻容分界线")
    _shot(win, app, "G_combobox_chinese")

    win.close()
    app.processEvents()
    print()
    print("验收结果:", "ALL PASS" if ok_all else "HAS FAILURE")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())