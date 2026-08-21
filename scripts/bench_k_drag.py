# -*- coding: utf-8 -*-
"""K 拖动性能基准（需求 6.6）：参考 Q / 阻容边界 ON 与 OFF 各 1000 次 K 更新。

统计：
- 每次 _do_update 的耗时（median / p95 / max，ms）
- family display rebuild 次数（plot.rebuild["family_path"]）
- boundary display rebuild 次数（plot.rebuild["boundary_path"]）
- engineering solve 次数（_recompute_engine 调用）
- result text rebuild 次数（_update_result_text 调用）

用法：
    python scripts/bench_k_drag.py
"""
from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC)

from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402


def _pct(hist, p):
    if not hist:
        return float("nan")
    s = sorted(hist)
    return s[min(len(s) - 1, int(p * len(s)))]


def _run_scenario(w, name, show_ref, show_bnd, n=1000):
    w.plot.set_display_state(show_reference=show_ref, show_boundary=show_bnd)
    w._on_slider_pressed()  # 真实拖动路径：_dragging=True + preview=True
    w._engine_dirty = True
    w._engine_pending = False

    # 计数探针
    engine_count = [0]
    text_count = [0]
    orig_engine = w._recompute_engine
    orig_text = w._update_result_text

    def _cnt_engine(*a, **k):
        engine_count[0] += 1
        return orig_engine(*a, **k)

    def _cnt_text(*a, **k):
        text_count[0] += 1
        return orig_text(*a, **k)

    w._recompute_engine = _cnt_engine
    w._update_result_text = _cnt_text

    fam0 = w.plot.rebuild["family_path"]
    bnd0 = w.plot.rebuild["boundary_path"]
    cur0 = w.plot.rebuild["current_path"]

    times = []
    for i in range(n):
        w.sliderK.setValue((i * 7) % 1001)
        w.dirty_k = True
        t0 = time.perf_counter()
        w._do_update()
        times.append((time.perf_counter() - t0) * 1000.0)
        if i % 50 == 0:
            w._result_timer.stop()
            w._on_result_timer()

    # 松手：退出 preview + 最终精确刷新
    w._on_released()

    w._recompute_engine = orig_engine
    w._update_result_text = orig_text

    fam = w.plot.rebuild["family_path"] - fam0
    bnd = w.plot.rebuild["boundary_path"] - bnd0
    cur = w.plot.rebuild["current_path"] - cur0
    print(f"[{name}] K updates={n}")
    print(f"    _do_update: median={_pct(times, 0.5):.3f}ms  "
          f"p95={_pct(times, 0.95):.3f}ms  max={_pct(times, 1.0):.3f}ms")
    print(f"    family display rebuild = {fam}   (期望 OFF 时≈0)")
    print(f"    boundary display rebuild = {bnd}   (期望 OFF 时≈0)")
    print(f"    current path rebuild = {cur}")
    print(f"    engineering solve = {engine_count[0]}   (期望 << {n})")
    print(f"    result text rebuild = {text_count[0]}   (期望 << {n})")
    print()


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_main.MainWindow()
    w.show()
    app.processEvents()
    w.resize(1420, 960)
    app.processEvents()
    w._refresh_timer.stop()

    # 场景 A：参考 Q ON + 阻容边界 ON
    _run_scenario(w, "A: 参考Q ON / 阻容边界 ON", True, True)
    # 场景 B：参考 Q OFF + 阻容边界 OFF
    _run_scenario(w, "B: 参考Q OFF / 阻容边界 OFF", False, False)

    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
