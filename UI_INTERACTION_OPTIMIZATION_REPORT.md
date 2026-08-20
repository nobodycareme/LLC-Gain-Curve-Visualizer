# LLC 增益曲线工具 —— UI 完整性 + 实时交互专项报告

> 本轮任务（四项目标）：① 彻底解决"图示不全"；② 重新设计阻容分界线视觉；
> ③ 真正解决拖动卡顿（三层分层缓存）；④ 新增 Curve Hover Inspector。
>
> 约束遵守：未改动任何 LLC 数学定义，未重引入 Matplotlib/NumPy runtime，
> 未缩减测试数量，显示采样不影响峰值/边界/Hover 的数学精度。
> 符号体系保持不变：`K = Lm/Lr`，`fn = fs/fr`，`Q = sqrt(Lr/Cr)/Re`。

---

## 一、图示完整性

### 图例修复

之前 `_draw_legend()` 存在 `rows = 2` 硬编码，即使 `legend_entries()` 准备了
15 条也无法全部铺开。本轮彻底移除固定行列约束，改为**自适应布局**：

- 依据 `PlotWidget` 可用宽度 ÷ 估算的单条目宽度 → 动态列数
 `cols = clamp(1, ⌊avail / (最长文字宽 + 图例间距)⌋, n)`；
- 行数 `rows = ceil(n / cols)`；
- 行高随 `devicePixelRatioF()` 放大，避免 High-DPI 烫行；
- 窗口 `resize` 后重新计算列/行数 → 图例自动重新布局；
- 图例渲染进独立透明条带 pixmap（键含 `Q/K/尺寸/列数`），fn 拖动零重建，
  只在 Q/K/尺寸变化时重建，避免图例"Q 文字不跟手"。

**最终图例条目（15 条，全部实际绘制）：**

```
1.  Q = 0.1           （参考曲线，tab10 系列 9 色）
2.  Q = 0.2
3.  Q = 0.5
4.  Q = 0.8
5.  Q = 1.0
6.  Q = 2.0
7.  Q = 5.0
8.  Q = 8.0
9.  Q = 10.0
10. 当前 Q 曲线：Q=0.5000   （黑色粗线）
11. 阻容分界线  ∠Zin = 0    （品红粗虚线）
12. fnp（并联谐振）        （红）
13. fnr=1（串联谐振）      （蓝）
14. △ 增益峰值
15. ◇ 工作点 fn
```

不遮挡核心曲线：绘图区顶部独立预留 legend band（`_plot_rect.top =
legend 高度 + 8px`），曲线区不再被图例长期覆盖。

### Y 轴刻度修复

之前写死 0~1.0。现改为标准 nice-number 算法：

```
raw_step = ymax / 目标刻度数(≈6)
取 mult ∈ {1, 2, 2.5, 5, 10} × 10^n 中使 (ymax/cand) ≤ 7.5 的最小者 → step
再按 step 从 0 递增到 ≥ ymax 生成刻度
```

例如 `ymax=2.2` → 刻度 `0, 0.5, 1.0, 1.5, 2.0, 2.5`；`ymax=50` → `0,5,...,50`；
`ymax=0.5` → `0,0.1,...,0.5`。主网格、轴刻度线、刻度文字三处共用同一
`_y_ticks()`，保证网格与刻度严格一一对应、文字不重叠。

### log 横轴 minor grid 修复

旧实现对每个 decade 未统一生成 `2..9×10^n` 导致映射错位/重复。现：
`_minor_log_freqs()` 对每个 decade 统一生成 `{2,...9}×10^n`，再逐个判断
是否落在 `[FN_MIN, FN_MAX]` 内筛选，无特殊 case、无重复。修正了"0.2~0.9 被
映射成 2~9、或第二 decade 重复"的问题，并有测试断言 `_map_x(0.2) ≠ _map_x(2.0)`。
次网格视觉改为浅灰实线（alpha 42），与主网格（alpha 60）形成可辨识层级。

### 曲线 clipping 修复

已删除类 `if m > top: started = False; continue` 的断线式裁剪。改为：

- `QPainterPath` 保留完整几何连续性（不因超 ymax 而中断 moveTo/lineTo）；
- 每条曲线统一 `painter.setClipRect(plot_rect)` 原生裁剪；
- 对远离可视区的巨值仅做边界夹紧（`clamp0/clamp1` 取图高 6 倍外），保证路径数值有效、
  不外溢；超 `Ymax/Ymin/Xmin/Xmax` 部分由 Qt 裁掉，**曲线不再缺线**。

逐项主动检查项：曲线不被图例覆盖（顶部独立 band）、不错误 clip（setClipRect）、
文字不被 widget 边界截断（图例/刻度文字判界夹紧）、右侧/顶部 label 不越界、
工作点/峰值标记在 clip 内、resize 后缓存键失效（base/semi/backdrop 全失效重建）、
High-DPI 下 `devicePixelRatioF` 统一缩放。

---

## 二、阻容分界线视觉

| 项 | 值 |
|------|------|
| 颜色 | `#D000C8`（高饱和品红/紫红），`BOUNDARY_LABEL_COLOR=#A00098` |
| 线宽 | `3.2 px` |
| 线型 | `Qt.DashLine`，dash pattern `[10.0, 4.0]` |
| 标签 | 线旁标注"阻容分界  ∠Zin=0"（白底 235 半透明圆角矩形，品红描边/文字，自动夹在图内） |

选色依据：品红（r 高、b 高、g 极低）与黑色当前 Q、红色 fnp、蓝色 fnr、参考 Q 族
九色均显著区分；白底高对比。线宽 3.2 + 长虚线保证一眼识别。测试 `test_boundary_*
` 断言颜色为高饱和品红、图例 dash 宽度 ≥ 3.0、与既有线色距离 ≥ 20。

---

## 三、性能优化

### 分层缓存架构

绘制拆成真正独立的三层，各自缓存，只有对应 dirty 才重建：

| 层 | 内容 | 缓存 | 触发重建 |
|----|------|------|----------|
| **Layer A0 backdrop** | 白底 + 主/次网格 + 坐标轴线 + 刻度文字 + 轴标签 | 独立 `QPixmap`，键=`(尺寸,ymax,DPR,字号)` | 仅尺寸/ymax/字号 |
| **Layer A base** | backdrop 合成 + 9 条参考 Q 路径 + 阻容边界 + fnp/fnr 竖线 | 独立 `QPixmap` | 仅 K/尺寸/ymax |
| **Layer B semi** | 当前 Q 曲线 + fnp/fnr/峰值 marker | 独立 `QPixmap`，键=`(尺寸,Q,K)` | 仅 Q/K/尺寸 |
| **Layer C overlay** | fn 竖线 + 工作点菱形 + Hover 高亮/Tooltip | 每帧轻绘制 | 每帧/鼠标移动 |

- **QPainterPath 缓存**：参考族 `_fam_paths`、边界 `_boundary_path`、当前 Q
  `_cur_path` 均固化为 `QPainterPath`；paintEvent 只重放，绝不逐点重建。
- **共享显示采样**：同一 rect 下 fn_curve 的像素 X 映射只算一次
  （`_display_sample` 缓存索引 + px），9 条参考族 + 当前 Q 曲线共享，避免
  每帧 ~16000 次 `math.log10` 重算。
- **显示采样 1600 点**（`plot_width ×1~1.5` 上限内，下限 600/上限 1800 语义）；
  数据数组仍保留 3000 点用于数学，峰值/边界/Hover 用精确公式计算，显示采样
  不影响数学结果。

### 各参数更新策略

| 拖动 | rebuild（1000 次实测计数） |
|------|------|
| **fn** | `family=0, boundary=0, current=0, base=0` —— 只更新 overlay |
| **Q** | `family=0, boundary=0`，仅 `current_path`/peak/工作点更新 |
| **K** | 才允许重算参考族 + 边界 + 当前 Q 路径（按约束） |

`sliderReleased`：已删除任何"全量 dirty"。释放时只冲刷尚未 flush 的最后一个值，
再执行极轻量文本/元数据刷新，绝不重算曲线族 → 无"松手顿一下"。

### 性能基准（`scripts/bench_drag.py`）

| 操作 | P50 | P95 | max | 参考族重建 | 边界重建 | 当前路径重建 |
|------|-----|-----|-----|-----------|---------|-------------|
| **fn 拖动**（400 次） | 1.451 ms | 3.730 ms | 8.99 ms | 0（仅初始 2） | 0 | 0 |
| **Q 拖动**（400 次） | 11.04 ms | 15.19 ms | 68.9 ms | 0 | 0 | 400 |
| **K 拖动**（200 次） | 66.86 ms | 84.93 ms | 122 ms | 200 | 200 | 400 |
| **Hover**（800 次） | 0.218 ms | 0.709 ms | 9.92 ms | 0 | 0 | 0 |

- fn 拖动 P95 **3.7ms**（< 8ms 目标，达 ~270FPS 绘制能力），只重播缓存 + 轻 overlay；
- Q 拖动 P50 11ms（~90FPS，肉眼无卡顿），且零参考族/边界重建；
- K 拖动 P50 67ms：其中 ~46ms 是"K 变化必须重算参考族"的纯数学成本
  （9×3000 + 边界 + 当前），剩余为路径重建 + 基底合成；backdrop 拆分省去重画
  网格/文字，共享 X 映射省去逐点 log10。符合"K 允许较重但跟手"约束；
- Hover P50 0.22ms，O(候选数) 级别，不影响任何曲线重建。

---

## 四、Curve Hover Inspector

### 命中算法

1. **X 反变换**：`pixel_to_fn(x)` 是 `_map_x(fn)` 的严格反函数
   （`fn = 10^(log10(FN_MIN) + frac·span)`），二者互逆、均有测试验证；
2. 对每候选曲线只算 **1 个标量数学点** `M = llc_gain(fn_mouse, K, Q)`
   （边界用 `boundary_gain(fn, K)`），成本 ≈ O(候选数)；
3. 像素映射 `screen_y = _map_y_full(M)`（不夹取，保留真实几何），
   计算 `distance_px = |screen_y - mouse_y|`；
4. **容差 8 CSS 像素**（逻辑坐标，天然兼容 High-DPI）；超容差 → 无 hover；
5. 候选仅：9 条参考 Q + 当前 Q + 阻容分界线；竖线/坐标轴/网格不识别为曲线。
6. **Tie-break**：像素距离差 < 1px 时按 `当前 Q > 阻容分界线 > 参考 Q` 选优，
   不按数组顺序（例如奇点 `(1,1)` 处当前 Q 优先）。

**明确禁止**“遍历 3000 采样点找最近数组元素”的低精度做法。

### 普通 Q 曲线 Tooltip

```
Q = 0.350
K = 5.000
fn = 0.8234
M = 1.1467
fs = 82.34 kHz     （= fn·fr，按 Hz/kHz/MHz 自动格式化）
区域：感性区        （∠Zin > 0）
```

区域判据来自 `input_region(fn,K,Q)`（即 Im(Zin) 符号），**不**按鼠标在边界
图形两侧猜测：`Im>tol 感性 / Im<-tol 容性 / |Im|≤tol 边界`。

### 阻容分界线 Tooltip

```
阻容分界线
∠Zin = 0
K = 5.000
fn = 0.7234
Mb = 1.0832
Qb = 0.4176
fs = 72.34 kHz
```

- `Qb(fn) = sqrt( ((K+1)fn² - 1) / (K²fn²(1-fn²)) )`（`q_boundary_for_fn`）；
- `Mb(fn) = sqrt( Kfn² / ((K+1)fn² - 1) )`（`boundary_gain`）；
- 边界点处 `Im(Zin(fn,K,Qb))≈0` 有测试验证；
- `fn→fnp⁺` 时 Mb→∞、`fn→1⁻` 时 Qb→∞：Tooltip 显示 `∞`/`无定义`，不出现
  NaN/1.#INF/Crash（`_fmt_bound_val` 处理 NaN/±inf）。

### 交互与绘制

- `setMouseTracking(True)`，mouseMove 即更新，无 16ms debounce；
- Hover 高亮圆点 radius 5px，继承命中曲线颜色并加白描边；边界用品红；
- Tooltip 用 QPainter 自绘圆角矩形（复用单一逻辑状态，不在此路径创建 QWidget/QLabel），
  默认鼠标右上方 +12/-12，右侧/顶部不足时翻转，绝不越出 widget；
- 局部 `update(union(old/new hover rect + tooltip rect))`；
- `leaveEvent` 清除 hover 并重绘。

---

## 五、Hover / 拖动专项测试

新增 `tests/test_ui_interaction.py`（25 项，全部通过）：

- 图示：`test_y_ticks_cover_full_range` / `test_y_ticks_high_ymax` / `test_y_ticks_small_ymax`
  / `test_log_minor_grid_each_decade_no_duplicates` / `test_x_forward_inverse_consistent`
  / `test_legend_shows_all_entries_adaptively` / `test_legend_resize_changes_layout`
  / `test_curve_renders_without_breaking_when_exceeding_ymax`；
- 边界视觉：`test_boundary_color_is_vivid_magenta` / `test_boundary_distinct_from_key_lines`
  / `test_boundary_legend_entry_thick_dashed` / `test_boundary_label_present`；
- 分层缓存/拖动：`test_slider_release_does_not_full_dirty` /
  `test_fn_drag_rebuilds_nothing`（1000 次） / `test_q_drag_rebuilds_only_current`
  （1000 次） / `test_k_drag_rebuilds_all`；
- Hover 8 项：`test_hover_inverse_transform` / `test_hover_hits_normal_q_curve` /
  `test_hover_beyond_tolerance_returns_none` / `test_hover_nearest_curve_wins` /
  `test_hover_tie_break_current_first` / `test_hover_boundary_qb_mb` /
  `test_hover_does_not_recompute_curves`（1000 次验证参考/边界/当前统计及路径重建计数均不变） /
  `test_hover_cache_stable`（1000 次后 `artist_census` 与 rebuild 计数均不变）；
- `test_fs_display_format_in_tooltip`（Hz/kHz/MHz 自动格式）。

---

## 六、测试与构建

- 修改前基线：`990` 项测试通过（上一轮数学稳定性专项结束点）。
- 修改后：**`1015` 项测试全部通过**（新增 `25` 项，无删除）。
- 构建：`build_exe.bat` 重建 `onedir` 与 `onefile` 两个 EXE，并各实际启动/存活/退出/
  二次启动全程验证。

---

## 七、完成标准对照

| 检查项 | 状态 |
|--------|------|
| 图例全部显示 + resize 后完整 | ✅ |
| Y 刻度完整正确 | ✅ |
| log minor grid 正确（每 decade 2..9，无重复） | ✅ |
| 曲线 clipping 正确、高峰不异常断裂 | ✅ |
| 阻容边界高对比品红粗虚线 + 图例明显 | ✅ |
| Static/Semi-dynamic/Overlay 三层 + QPainterPath 缓存 | ✅ |
| fn 变化零曲线重建；Q 变化零参考族重建；sliderReleased 无全量 dirty | ✅ |
| Hover 识别 9 参考 Q + 当前 Q + 阻容分界，数学精确值，不依赖离散采样 | ✅ |
| fs 正确显示、感性/容性区域正确、边界 Qb/Mb 正确 | ✅ |
| Hover 不触发重型曲线重算、缓存不增长、不闪烁 | ✅ |
| 原测试全通过 + 新测试通过 | ✅ |
| onedir 实际 GUI 验收 | ✅（构建脚本启动/存活/二次启动验证） |
| onefile 实际 GUI 验收 | ✅（同上） |
| 两个最终 EXE 已重建 | ✅ |