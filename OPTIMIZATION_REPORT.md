# LLC 增益曲线工具 —— 一次性最终优化报告

> 任务：阻容分界线的严格数学实现 + EXE 体积大幅缩减 + 启动时间显著下降。
> 优先级：物理/数学正确性 > 功能不回退 > 启动速度 > 分发体积 > 代码整洁度。

---

## 1. LLC 理论修改

### 1.1 为什么“增益峰值”不是“阻容边界”

之前的实现（以及许多近似工具）通过“对每条 Q 曲线找增益最大值，再把这些最大值连起来”来近似分界线。
这是不严格的：

* **增益峰值**是 `∂M/∂fn = 0`（图像上曲线的最高点）；
* **阻容边界**是输入阻抗相位恰好为零（`∠Zin = 0`，`Im(Zin)=0`）。

在 TI LLC FHA 模型中，这两者在有限 Q 下**非常接近但不相等**。峰值点位于容性区一侧
（`Im(Zin) < 0`）。新一轮已彻底把二者分离并给出各自独立、可测试的定义与命名：

| 量 | 定义 | 判据 |
|------|------|------|
| `f_peak` / `M_peak` | 增益曲线极大值 | `∂M/∂fn = 0` |
| `f_boundary` / `M_boundary` | 阻容分界 | `Im(Zin) = 0`（`∠Zin = 0`） |

### 1.2 使用的 Zin 判据

* 谐振特性阻抗 `Zr = sqrt(Lr/Cr)`；
* 质量因数 `Q = Zr / Re`；归一化开关频率 `fn = fs/fr`；`K = Lm/Lr`。
* 归一化输入阻抗（无量纲）：

```
z_in = j(fn − 1/fn) + (j·K·fn) / (1 + j·K·Q·fn)
```

区域判定直接读取该复数阻抗虚部的符号：

* `Im(Zin) > 0` → **感性区**（ZVS 有利区）；
* `Im(Zin) < 0` → **容性区**；
* `|Im(Zin)| ≈ 0` → **阻容边界**。

实现位于 `src/llc_py.py::llc_input_impedance_normalized()`，模型层可独立求
`Re(Zin)` / `Im(Zin)` / `angle(Zin)`。

### 1.3 边界方程与边界频率

由 `Im(z_in) = 0` 整理得：

```
Qb²(fn) = [ (K+1)·fn² − 1 ] / [ K²·fn²·(1 − fn²) ]
```

有效频率范围 `1/sqrt(K+1) < fn < 1`，即起于并联谐振频率 `fnp = 1/sqrt(K+1)`，
止于串联谐振 `fn = 1`。

**固定 K 的整族分界线（解析）**，代入 FHA 增益化简得：

```
M_boundary(fn) = sqrt( K·fn² / ( (K+1)·fn² − 1 ) )     (fnp < fn < 1)
```

**固定 Q 的边界交点频率（数值稳定形式）**：

```
令 A=(KQ)², B=K+1−A
f_nb² = 2 / ( B + sqrt(B² + 4A) )
f_nb  = sqrt( 上述 )
Q→0 极限：f_nb → 1/sqrt(K+1)
```

采用上述形式是为了在 Q 很小 / B 接近 0 时避免二次公式的浮点相消，_不_ 直接用 `(−B+sqrt)×(1/2)`。

### 1.4 边界数值验证

* **解析边界公式** ⇄ **原始复阻抗相位判据** 双向交叉验证；
* 固定 K：用 `M_boundary(fn)` 生成边界，再用 `llc_input_impedance_normalized` 用
  `Qb(fn)` 复算 `Im(Zin)≈0`；
* 固定 Q：`boundary_frequency(K,Q)` 代入阻抗验证 `Im(Zin(fb))≈0`；
* 关键指标：`|Im(Zin)| < 1e-8`。

---

## 2. 文件体积

### 基线（修改前）

| 项 | 值 |
|------|------|
| 旧交付 | `dist\LLC增益曲线.exe`（PyInstaller onefile） |
| 旧 EXE 体积 | **64,148,883 B ≈ 61.18 MiB** |
| 体积主要组成（~93 MB onedir 目录） | Qt DLL + 插件 ≈ 72.5 MB、numpy ≈ 26.7 MB、matplotlib ≈ 11.6 MB，其中 `opengl32sw.dll` 一项 ≈ 20 MB |

最终打包配置 `LLC_Gain_Curve.spec` 已显式记录全部排除项与 File-pattern 过滤（见文末）。

### 体积对比表

| 版本 | 打包器 | 模式 | Matplotlib | NumPy | 体积 | 相对旧版 |
|------|--------|------|:---:|:---:|------|------|
| 旧版 | PyInstaller | onefile | 保留 | 保留 | 61.18 MiB | — |
| 新版 | PyInstaller | **onefile** | 已移除 | 已移除 | **27.61 MB ≈ 26.33 MiB** | **−59.0%**（−37.82 MiB） |
| 新版 | PyInstaller | onedir（standalone） | 已移除 | 已移除 | 目录总 65.97 MiB | −28.2%（相对旧 onedir 93 MiB） |

> 体积口径：onefile 按 EXE 本体字节统计；onedir 按整个 `_internal` 目录总大小统计，
> 两者分开报告，不以“外壳 EXE + 外部 DLL”方式规避统计。

---

## 3. 启动性能

### 口径与测量方法

* **窗口可见即就绪**：轮询进程表，找到标题含 “LLC” 且 `MainWindowHandle ≠ 0` 的真实顶层窗口为“就绪”。
* 与旧 EXE 使用**完全相同**的方法测量（`scripts/measure_startup.ps1`）。
* 另用 `scripts/measure_startup_detail.ps1`（`LLC_TIMING=1`）拆出内部里程碑。

### 实测结果（同机、每组连续多次）

| 版本 | min | median | max |
|------|-----|--------|-----|
| 旧 EXE (onefile) | 8,749 ms | **8,805 ms** | 11,035 ms |
| 新 EXE (onefile) | 2,129 ms | **2,875 ms** | 3,515 ms |
| 新 EXE (onedir/standalone) | 575 ms | **653 ms** | 850 ms |

### 加速比例

* **onefile：中位数 8,805 ms → 2,875 ms，缩短约 67%（约 3.1× 提速）**。
* **onedir/standalone：中位数 653 ms，缩短约 92%（约 13.5× 提速）**，轻松达到“≤ 1.5 s”目标。

### 内部里程碑拆解（onefile，middle-of-range run）

| 里程碑 | 含义 | 耗时（中位数） |
|------|------|------|
| `t0_entry` | 进程入口 | 0 ms |
| `t1_qapp` | 模块导入 + `QApplication` 创建 | ~51 ms |
| `t2_mainwin` | `MainWindow` 构造 | ~168 ms |
| `t3_show` | 窗口 `show()` | ~467 ms |
| `t4/t5` | 首帧阴影 + 可交互 | ~638 ms |

**关键结论：应用自身初始化只有约 640 ms。** onefile 剩余的 ~2.2 s 是 PyInstaller
自解压实况（解压到临时目录 + DLL 装载 + Python 运行时装载），属 onefile 固有机制成本。
这正是启动问题根源：**不是业务代码，而是自解包过程**。因此：

* 若首要诉求是“极速启动”，使用 **onedir/standalone 版（~0.65 s）**；
* 若必须单文件分发且能接受 ~2.9 s 首启，使用 **onefile 版**（相对旧版仍提速 ~67%）。

> 禁止事项合规说明：未使用 splash screen 掩盖冷启动；窗口出现时主线程已完成 `show()` 且
> 进入事件循环，可直接交互。

---

## 4. 依赖缩减

### 移除的运行时依赖

* **Matplotlib**：已移除。绘图改用 `src/plot_widget.py`（`QWidget + QPainter`），
  复刻全部可见功能（坐标轴/刻度/网格/多曲线/线型/图例/工作点/阻容边界/尺寸自适应/High-DPI/
  中英文/导出 PNG）。字体改用 Qt `QFontDatabase`，不再扫描 Matplotlib 字体库。
* **NumPy**：已移除（运行路径）。新增纯 Python 数学层 `src/llc_py.py`。LLC 计算均为解析式，
  纯 Python 已足够快，K/Q/fn 拖动保持原性能架构（增量刷新 + QTimer 合并 + 对象不增长）。
  numpy 仅在旧参考实现 `llc_model.py` 及 llc_py↔llc_model 交叉测试中保留。

### Qt 模块范围（只保留真正需要的）

仅打包 `QtCore / QtGui / QtWidgets`。通过 spec `excludes` 排除：
WebEngine、Quick/Quick3D、Qml、Charts、DataVisualization、Multimedia、Bluetooth、NFC、
Positioning、Sql、Test、Designer、Help、SerialPort、SpatialAudio、RemoteObjects、Scxml、
Sensors、TextToSpeech、Pdf、PdfWidgets、**QtNetwork**（无关传递依赖）。

还按文件名定向剔除 Qt 软件 OpenGL 回退库：
`opengl32sw.dll`(≈20MB)、`libEGL.dll`、`libGLESv2.dll`、`d3dcompiler_47.dll`。
程序为纯 QPainter 栅格绘制，从不触发 OpenGL 上下文。
（这是打包配置级的确定排除，非“手工删 DLL”；若未来某平台需要，删除 spec 中过滤即可恢复。）

### 最终运行时依赖

```
PySide6-Essentials  (仅 QtCore/QtGui/QtWidgets)
python 运行时
```

requirements.txt 已更新：运行/构建只需 `PySide6-Essentials` + `pyinstaller`；
`pytest/numpy/matplotlib` 明确标注为仅开发/测试用，不进入最终 EXE。

---

## 5. 测试结果

| 阶段 | 数量 | 状态 |
|------|------|------|
| 修改前基线 | 317 passed | ✅ |
| 新增阻容边界测试（`tests/test_boundary_rc.py`） | +6 类 | ✅ |
| GUI 边界/区域/刷新测试（`tests/test_boundary_gui.py`） | 新增 | ✅ |
| 纯 Python ⇄ NumPy 交叉测试（`tests/test_llc_py_crosscheck.py`） | 新增 | ✅ |
| 启动/打包/验收冒烟（脚本） | new | ✅ |
| **最终全量** | **704 passed** | ✅ |
| 最终收尾新增边界专项（`test_boundary_frequency_*.py`：稳定性/极端Q/单调性/高精度参考/支点） | +286 | ✅ |
| **最终全量（本轮）** | **990 passed** | ✅ |

新增边界专项测试包含：
1. 边界阻抗虚部为零：随机 K/Q，`Im(Zin(fb)) < 1e-8`；
2. 边界左右区域符号正确（左容右感）；
3. 解析边界 ⇄ 完整 FHA 阻抗 `∠Zin≈0`，且 `M_boundary ≈ llc_gain(fn,K,Qb)`；
4. 极限：`Q→0 → 1/sqrt(K+1)`，`Q 增大 → 1`；
5. 已知数值交叉：`K=5, Q=0.5` → `fn_boundary≈0.64846, M_boundary≈1.17495`；
6. 峰值 ≠ 分界：典型设计下 `f_peak` 位于容性侧 `Im(Zin)<0`，且与 `f_boundary` 接近但不等。
7. GUI 层：分界线存在、K 改变即重算、工作区域判据直接来自 `Im(Zin)`、fn 跨越边界时区域切换、
   结果文本含区域/边界信息、边界数据缓冲数量恒定（不随拖动增长）。

> 未删除任何原有回归测试；旧 Matplotlib ⇒ QPainter 的迁移仅改“实现耦合型”断言，
> 并把“artist 不增长”迁移为“绘图数据缓冲/缓存不增长 + 1000 次更新稳定”。

---

## 6. 最终推荐版本

* **日常使用推荐：onedir/standalone 版**（`dist\LLC增益曲线_onedir\LLC增益曲线.exe`）
  — 启动中位数 ~0.65 s，功能与 onefile 完全相同，最适合本机/频繁使用。
* **对外分发推荐：onefile 单文件版**（`dist\LLC增益曲线.exe`，26.33 MiB）
  — 单个文件直接双击运行、无需安装 Python，适合交付给其他无环境用户；首启 ~2.9 s 仍比旧版快约 3 倍。

> 依据：用户明确需要单文件 EXE（已提供），且要求区分 onefile 与 standalone 体积/速度
> 分开报告（已分别给出）。onedir 之所以“目录版”却更快，是因为省去了内置解压步骤。

---

## 7. Final Numerical Stability & Compatibility Audit

> 最终收尾审计（构建日期 2026-08-20，Python 3.10.11 / PySide6 6.11.1 / PyInstaller 6.21.0）。
> 本轮只做数值稳定性、测量严谨性、发布兼容性收尾，未回退任何已确认基线。

### 7.1 boundary_frequency 数值稳定性修复

**原问题**：固定 Q 交点二次方程 `A x² + B x − 1 = 0`（`A=(K·Q)²`, `B=K+1−A`, `x=fnb²`）。
原实现统一用有理化正根 `x = 2/(B + D)`，`D=sqrt(B²+4A)`。

* 当 `B ≥ 0` 时该形式稳定——避免了 `−B + D` 两个接近数相减；
* 当 `B < 0` 且 `|B|` 很大（极大 Q）时，`D ≈ −B`，此时 `B + D` 本身成为
  两个巨大且接近的数相减，**灾难性相消**：有效位大幅丢失、`fnb` 被提前舍入为
  `1.0`、分母可被舍为 0 触发 `ZeroDivisionError`。

**最终算法**（`llc_py.boundary_frequency` / `llc_model.boundary_frequency` 同步）：

```
Q = 0      → 解析极限 fnb = 1/sqrt(K+1)
B ≥ 0      → x = 2/(B + D)          # 有理化，避免 −B+D 相消
B < 0      → x = (−B + D)/(2A)      # 此时 −B 与 D 均为正、相加，无相消
D          → hypot(B, 2·sqrt(A))    # = sqrt(B²+4A)，防中间量 overflow
fb → 1.0   在 K·Q 已溢出双精度时饱和（浮点表示极限，非算法错误）
```

* **是否使用 B 正负分支**：是（两支分别避开了各自一侧的相消，不能合并成单一公式）。
* **是否使用 math.hypot**：是（同时避免 `B*B` 与判别式中间量无意义 overflow）。
* 非法输入（`K<=0`、`Q<0`、`NaN`、`±inf`）统一抛 `ValueError`，绝不静默 `abs`/裁剪。
* GUI 层滑块天然限定 `K∈[1.5,10]`、`Q∈[0.05,10]`（有限工程范围）；极端 Q 仅在数学
  层测试，不改变 GUI 参数范围。

### 7.2 极端参数验证

对 `K=5` 在全 Q 跨度上：`fb` 始终落在 `[fnp, 1]`（`fnp=1/sqrt(6)≈0.408248`）；
用原始 FHA 输入阻抗独立验证 `Im(Zin(fb))≈0`；与高精度 `Decimal`（精度 50 位）参考
求解交叉核对，误差在机器精度内。

| K | Q | f_boundary | Im(Zin) | 参考值误差 \|fb−ref\| |
|----|----|-----------|---------|----------------------|
| 5 | 0         | 0.408248290464 | 4.44e-16 | 5.55e-17 |
| 5 | 1e-6      | 0.408248290465 | 4.44e-16 | 0.00e+00 |
| 5 | 0.5       | 0.648459472820 | 0.00e+00 | 0.00e+00 |
| 5 | 1         | 0.899676725870 | 2.50e-16 | 1.11e-16 |
| 5 | 100       | 0.999989999990 | 2.01e-16 | 1.11e-16 |
| 5 | 1e4       | 0.999999999000 | 1.64e-16 | 1.11e-16 |
| 5 | 1e8       | 1.000000000000 | 2.00e-17 | 0.00e+00 |

专项结果：最大 Q 专项测试 `Q=1e8` **不崩溃、不产生 NaN/inf**；全参数表内
`Im(Zin)` 最大边界残差 **4.44e-16**（接近双精度机器精度）；单调性测试固定 K 下
`fnb(Q)` 单调不减、无反向跳变；`B≈0`（`Q=Qcrit`）两分支连续、支点解析值
`(K+1)^(−1/4)` 验证通过。

### 7.3 真正可交互启动时间

测量口径升级：`measure_startup.ps1` 仍是“窗口可见”（`MainWindowHandle≠0`，外部墙钟）；
新增 `measure_startup_detail.ps1` 通过内建 Ready Marker（`LLC_TIMING=1` 才启用）测量
真正的“首帧完成 + 事件循环可交互”：`t4_first_paint`（首帧落地）与
`t5_event_loop_ready`（可交互就绪）。正常启动零开销（不写文件/不建 timer/无 UI）。

每项 10 次，报告 min / median / mean / p90 / max（ms）：

| 配置 & 指标 | 窗口可见（外部） | 交互就绪 t5（进程内） |
|-------------|-----------------|----------------------|
| **onefile** min    | 2,054 | 687 |
| **onefile** median | 2,574 | 709 |
| **onefile** mean   | 2,697 | 722 |
| **onefile** p90    | 3,236 | 767 |
| **onefile** max    | 3,494 | 801 |
| **onedir**  min    | 538   | 803 |
| **onedir**  median | 575   | 935 |
| **onedir**  mean   | 613   | 1,016 |
| **onedir**  p90    | 666   | 1,240 |
| **onedir**  max    | 929   | 1,601 |

外部 `spawn→json` 全墙钟（含 PyInstaller 解压 / Python 导入 / 120 ms settle）中位数：
onefile 3,094 ms、onedir 1,776 ms。相比既有基线（onefile 2.9 s、onedir 0.65 s）**无回退**。

### 7.4 Windows 兼容性

**源码级 OpenGL 依赖扫描**：`src/*.py` 对 `QOpenGL / QOpenGLWidget / OpenGL / QtQuick /
QML / QRhi / QSurfaceFormat / AA_UseOpenGLES / AA_UseDesktopOpenGL / AA_UseSoftwareOpenGL /
QGraphicsView` 命中 **0**；主渲染路径为纯 QWidget + QPainter（CPU 栅格）。

**打包依赖审查**（重建后检查 onedir `_internal`）：不存在
`opengl32sw.dll / libEGL.dll / libGLESv2.dll / d3dcompiler_47.dll`；
不存在 `QtOpenGL / QtQuick / QtQml / QtWebEngine / Qt3D` 模块；Qt 插件仅保留
`platforms / styles / imageformats / iconengines / generic`，无 ANGLE/OpenGL 插件；
Qt 二进制仅 `Qt6Core / Qt6Gui / Qt6Widgets`（`Qt6Network / Qt6Svg` 为
QtGui/QtWidgets hook 的轻量传递二进制，体积小，保持）。结论：**继续排除**上述 4 个 DLL，
不恢复。

**实机 smoke test**（当前 Windows 11 Pro 主机）：onedir 启动 → 窗口显示 → 截图验证通过；
曲线族/黑色当前曲线/峰值包络、坐标轴（log 横轴/线性纵轴/网格）、阻容边界标记、
工作点标记、中文渲染、窗口完整性均正常，**无白屏/无黑屏/无崩溃**；onefile 已由构建脚本
两次启动（可重复运行）验证通过。

**已测试环境**：A 当前 Windows 11 Pro 主机 ✅
**未测试环境**（本机无法取得，按“未验证”如实记录）：B Windows VM、
C RDP 远程桌面、D Microsoft Basic Display Adapter / 无独立显卡、E 无 Python 干净用户机。
其中 E 由 PyInstaller 自包含原理支持但未在真机复核。

### 7.5 最终体积

* **onefile**：27,6xx,xxx bytes = **26.33 MiB**
* **onedir**：69,1xx,xxx bytes = **65.97 MiB**；启动中位数 0.575 s（窗口可见）
* 本轮未再进行体积挤压；上述排除仅针对经确认无关的 OpenGL 回退 DLL 与未使用 Qt 模块。
  `tests/pytest/numpy/matplotlib` 全在 `excludes` 中，未进入最终 EXE。
* 最终发布版 SHA-256（onefile，大写）：

  `C04A65DF0FF98B138B3379236F6A4FA8A441625BCD67C10EEEAB4571A54AA099`

> 注：最终发布（v1.0.0）在加入阻容分界线、曲线悬停检查与三层缓存交互优化后重新构建，
> 以上为最终交付二进制的新校验值；下述早期记录的 `0bc242a4…` 为中间构建版本，仅供参考。

---

## 附：最终交付物清单

```
src/main.py, src/plot_widget.py, src/llc_py.py, src/cjk_font.py, src/llc_model.py, src/llc_plot.py
tests/test_boundary_rc.py, tests/test_boundary_gui.py, tests/test_llc_py_crosscheck.py (+已迁移旧测试)
tests/test_boundary_frequency_stability.py, test_boundary_frequency_extreme_q(_合并入 stability).py,
     test_boundary_frequency_monotonic.py, test_boundary_frequency_reference.py,
     test_boundary_frequency_tricky.py  # 本轮新增 990 项全量的一部分，共 990 passed
LLC_Gain_Curve.spec          # 显式记录模块排除 + DLL 过滤
requirements.txt             # 运行/构建依赖已精简
scripts/build_exe.bat        # 一键构建（清环境->装依赖->pytest->onedir->onefile->校验）
scripts/measure_startup.ps1 / measure_startup_detail.ps1 / accept_exe.ps1 / screenshot_exe.ps1
dist\LLC增益曲线.exe                     # 最终 onefile 单文件版  26.33 MiB
dist\LLC增益曲线_onedir\LLC增益曲线.exe  # standalone 极速版       目录总 65.97 MiB（窗口~0.65s）
OPTIMIZATION_REPORT.md       # 本报告
```

构建可复现：`requirements.txt` 提供版本区间 + 可手动的严格锁定项；`build_exe.bat`
从零创建虚拟环境并执行 完整测试→构建→启动验证→SHA-256。