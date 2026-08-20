# -*- coding: utf-8 -*-
"""拖动 / Hover 性能基线采集（offscreen 离屏）。

用法：
    python scripts/bench_drag.py
    python scripts/bench_drag.py --real   # 用真实平台窗口（需显示器）

输出每个场景 paint P50/P95/max（ms）与各层重建次数。
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, SRC)

from PySide6.QtCore import QPointF  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from llc_py import llc_gain as L  # noqa: E402


def _pct(hist, p):
    if not hist:
        return float("nan")
    s = sorted(hist)
    return s[min(len(s) - 1, int(p * len(s)))]


def _report(name, samples, rebuild):
    n = len(samples)
    print(f"[{name}] n={n}  P50={_pct(samples, 0.5):.3f}ms  "
          f"P95={_pct(samples, 0.95):.3f}ms  max={_pct(samples, 1.0):.3f}ms")
    print(f"    rebuild: {rebuild}")


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    w = app_main.MainWindow()
    w.show()
    app.processEvents()
    plot = w.plot
    plot._collect_perf = True
    # 先建好基底
    plot._ensure_base()
    plot._paint_ms.clear()

    def flush(n=1):
        for _ in range(n):
            app.processEvents()

    # ---- fn 拖动 ----
    for i in range(400):
        w.sliderFn.setValue((i * 7) % 1001)
        w._do_update()
        flush()
    _report("fn drag", plot._paint_ms, plot.rebuild)
    plot._paint_ms.clear()

    # ---- Q 拖动 ----
    for i in range(400):
        w.sliderQ.setValue((i * 3) % 1001)
        w._do_update()
        flush()
    _report("Q drag", plot._paint_ms, plot.rebuild)
    plot._paint_ms.clear()

    # ---- K 拖动 ----
    for i in range(200):
        w.sliderK.setValue((i * 5) % 1001)
        w._do_update()
        flush()
    _report("K drag", plot._paint_ms, plot.rebuild)
    plot._paint_ms.clear()

    # ---- Hover ----
    plot._hover_ms.clear()
    pr = plot._plot_rect(plot.width(), plot.height())
    for i in range(800):
        fn = 0.3 + 7.0 * (i / 800)
        px = plot._map_x(fn, pr)
        ps = plot.pixel_to_fn(px, pr)
        py = plot._map_y_full(L(ps, plot.K, plot.Q), pr)
        plot._update_hover(QPointF(px, py))
    _report("hover", plot._hover_ms, plot.rebuild)

    w._refresh_timer.stop()
    w.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())