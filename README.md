<div align="center">

# LLC 谐振变换器增益曲线可视化工具

**Interactive FHA Gain-Curve Visualizer for LLC Resonant Converters**

简体中文 | [English](README_EN.md)

[![Latest Release](https://img.shields.io/badge/Release-v1.0.0-blue.svg)](https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer/releases/latest)
[![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11%20x64-informational)](#快速下载)
[![Python](https://img.shields.io/badge/Python-3.10--3.12-3776AB)](requirements.txt)
[![PySide6](https://img.shields.io/badge/PySide6-6.7%2B-41CD52)](requirements.txt)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-1015%20passed-brightgreen.svg)](#测试与验证)
[![CI](https://img.shields.io/github/actions/workflow/status/nobodycareme/LLC-Gain-Curve-Visualizer/tests.yml?label=CI)](https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer/actions/workflows/tests.yml)
[![Status](https://img.shields.io/badge/Status-Stable-brightgreen.svg)](#)

一个用于研究 LLC 谐振变换器 **FHA（基波近似）增益特性** 的交互式 Windows 桌面工具，
面向电力电子专业学生、开关电源工程师以及 LLC 参数设计与教学活动。

</div>

---

## 1. 项目简介

本项目是一个用于研究 LLC 谐振变换器 FHA（基波近似, First Harmonic Approximation）
电压增益特性的交互式 Windows 桌面工具。它基于经典 LLC 基波分析方法，
将增益 `M(fn, K, Q)` 表示为归一化频率、电感比与品质因数的函数，
通过实时可调滑块与对数坐标绘制的多曲线族，直观呈现参数变化对增益特性、
谐振点与感性/容性工作区的影响。

**适用对象：**

- 电力电子专业学生；
- 开关电源工程师；
- LLC 参数设计与教学；
- 面试与课程学习；
- 初步参数敏感性分析。

> 这是一款**增益曲线可视化与分析工具**，用于参数趋势研究与教学，并非完整的
> 电源自动设计软件。

## 2. 界面预览

程序主界面（最终版真实运行截图，含顶部完整图例与品红阻容分界线）：

![Main interface](docs/images/main-interface.png)

## 3. 核心功能

- 多条固定参考 Q 曲线（Q = 0.1, 0.2, 0.5, 0.8, 1.0, 2.0, 5.0, 8.0, 10.0）；
- 当前 Q 曲线突出显示（黑色粗线）；
- K = Lm/Lr、Q、fn = fs/fr 实时调节；
- **精确阻容分界线**（感性区 / 容性区边界，见第 5 节）；
- 感性区 / 容性区实时判断（基于输入阻抗相角 sign(Im(Zin))）；
- 并联谐振点 fnp、串联谐振点 fnr = 1 标记；
- 当前增益峰值搜索（与阻容边界严格区分）；
- 当前工作点实时标记（随 fn 滑动沿当前曲线移动）；
- **Curve Hover Inspector**：鼠标悬停任意增益曲线，实时显示该数学点参数
  （见第 6 节）；
- 实际开关频率换算（fs = fn · fr）；
- 中文桌面界面；
- 对数频率横轴、动态规整 Y 轴刻度、正确对数次网格、完整曲线裁剪；
- High-DPI 支持；
- Windows 单文件 EXE（无需 Python，开箱即用）。

## 4. 数学模型

符号体系（统一采用，全程保持一致）：

| 符号 | 定义 | 物理意义 |
|------|------|----------|
| `K` | `Lm / Lr` | 励磁电感比（无单位） |
| `fn` | `fs / fr` | 归一化开关频率（无单位） |
| `Q` | `sqrt(Lr / Cr) / Rac` | 品质因数（负载因子） |
| `fr` | `1 / (2π√(Lr·Cr))` | 串联谐振频率（Hz） |
| `fp` | `1 / (2π√((Lr + Lm)·Cr))` | 并联谐振频率（Hz） |
| `M(fn, K, Q)` | 增益 | FHA 电压增益（无量纲） |

**FHA 增益公式：**

```
         K · fn²
M = ---------------------
    sqrt( ((1+K)·fn² − 1)² + (Q·K·fn·(fn² − 1))² )
```

**谐振点（归一化频率）：**

```
并联谐振：fnp = fp/fr = 1 / sqrt(1 + K)
串联谐振：fnr = fr/fr = 1
```

**实际频率换算：**

```
fs    = fn      · fr
fp    = fnp     · fr
fpeak = fn_peak · fr
```

其中 `fn_peak` 为曲线增益峰值对应的归一化频率（数值搜索得到，高精度）。

> **重要**：本项目统一采用 `K = Lm/Lr`（电感比）、`fn = fs/fr`（归一化频率）、
> `Q = sqrt(Lr/Cr)/Rac`（品质因数）。文献中使用其他 K/Q 定义所得曲线会不同，
> 使用本工具时请勿与不同定义混淆。

## 5. 精确阻容分界线（∠Zin = 0）

当前版本的阻容分界线**不是**通过"连接各增益峰值"近似得到，而是严格基于 LLC
FHA 输入阻抗虚部为零计算：

```
Im(Zin(fn, K, Q)) = 0
```

依此在图中绘制：

- `Im(Zin) > 0` → **感性区**（Zin 呈感性）；
- `Im(Zin) < 0` → **容性区**（Zin 呈容性）。

图上以**高对比品红粗虚线**标出该分界线并在线旁标注"阻容分界 ∠Zin=0"，鼠标悬停
其上可查看对应 `M_boundary` 与 `Q_boundary`。

> **注意**：增益峰值和阻容分界线在曲线上通常非常接近，但属于两个不同概念——
> 峰值是 `∂M/∂fn = 0` 的位置，阻容边界是 `Im(Zin) = 0` 的位置。本工具对二者
> 严格分别计算与标记。

## 6. Curve Hover Inspector

将鼠标移到**任意参考 Q 曲线、当前 Q 曲线或阻容分界线**附近，无需点击，即可
实时显示该鼠标横坐标对应数学点的参数。

普通 Q 曲线悬停显示：

```
Q  = 0.350
K  = 5.000
fn = 0.8234
M  = 1.1467
fs = 82.34 kHz
区域：感性区
```

阻容分界线悬停显示：

```
阻容分界线
∠Zin = 0
K  = 5.000
fn = 0.7234
Mb = 1.0832
Qb = 0.4176
fs = 72.34 kHz
```

- Hover 数值通过数学模型按鼠标横坐标**实时计算**，不依赖最近的离散绘图采样点；
- 区域判定来自输入阻抗 `Im(Zin)` 的符号，而非图形坐标猜测；
- 命中容差 8 逻辑像素，天然兼容 High-DPI；
- 数据细节见 [UI_INTERACTION_OPTIMIZATION_REPORT.md](UI_INTERACTION_OPTIMIZATION_REPORT.md)。

## 7. 参数影响

- 修改 `K`：改变电感比，影响 **全部**增益曲线族（整族曲线同时重算）；
- 修改 `Q`：改变当前负载条件，只有 **当前 Q 曲线** 变化（固定参考曲线族不变）；
- 修改 `fn`：改变工作点，工作点沿当前 Q 曲线移动（不重算任何曲线）；
- 修改 `fr`：只改变实际频率换算（`fs = fn · fr`），不改变归一化增益曲线形状。

（具体影响幅度依赖其他参数的取值，以上为趋势性描述，以程序计算结果为准。）

## 8. 性能与实现

```
绘图后端：PySide6 QWidget + QPainter（无 Matplotlib）
运行时：  无需 NumPy、无需 Matplotlib
绘图架构：Static / Semi-Dynamic / Overlay 三层缓存
```

- fn 滑动只更新动态 overlay，零曲线重算；
- Q 滑动只重算当前曲线，参考族与边界不动；
- K 滑动才重算参考族与边界；
- 滑块释放不做全量重算，避免"松手顿一下"。

详细技术过程与 benchmark 见
[OPTIMIZATION_REPORT.md](OPTIMIZATION_REPORT.md) 与
[UI_INTERACTION_OPTIMIZATION_REPORT.md](UI_INTERACTION_OPTIMIZATION_REPORT.md)。

## 9. 快速下载

最新稳定版：**v1.0.0**

[![Download](https://img.shields.io/badge/Download-v1.0.0-green.svg)](https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer/releases/latest)

### 普通用户单文件版（推荐）

资产：`LLC-Gain-Curve-Windows-x64.exe`

- 单个 EXE，下载后直接双击运行；
- 无需安装 Python；
- 方便下载与分享；
- 首次启动需解包，启动相对 onedir 稍慢。

### 极速版（onedir）

资产：`LLC-Gain-Curve-Windows-x64-onedir.zip`

- 解压后运行其中的 `LLC增益曲线.exe`；
- 启动明显更快，适合频繁使用；
- 目录内包含运行所需 DLL，**必须保持整个解压目录结构完整**，不能只把其中的
  EXE 单独拿走。

> 两者功能完全一致，仅启动体验与体积形态不同。

## 10. 使用方法

1. 从 [Releases](https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer/releases/latest)
   下载 EXE（或 onedir 压缩包）；
2. 验证 SHA-256（见 [第 11 节](#11-sha-256-验证)）；
3. 双击运行（onedir 需先解压）；
4. 调节 K、Q、fn 滑块，观察曲线、谐振点、阻容分界线与增益峰值；
5. 鼠标悬停任意曲线，查看实时精确参数。

## 11. SHA-256 验证

在 PowerShell 中执行：

```powershell
Get-FileHash ".\LLC-Gain-Curve-Windows-x64.exe" -Algorithm SHA256
```

本项目 v1.0.0 官方发布的 onefile EXE SHA-256：

```
c04a65df0ff98b138b3379236f6a4fa8a441625bcd67c10eeeab4571a54aa099
```

也可直接比对 Release 附件 `SHA256SUMS.txt` 中记录的 onefile 与 onedir ZIP 的摘要。

## 12. Windows 安全提示

- 当前 EXE 未经代码签名，Windows SmartScreen 可能显示"未知发布者"提示；
- 请始终从本仓库 **官方 Releases 页面** 下载，不要使用第三方镜像；
- 任何版本都可用上一节提供的方式（SHA-256）校验文件完整性；
- 不要关闭或禁用杀毒软件；若杀毒软件报警，请以实际文件哈希核实来源后自行判断，
  并可在 Issue 中反馈。

## 13. 从源码运行

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
python src\main.py
```

也可以直接运行 `scripts\run_source.bat`（脚本会自动创建虚拟环境并启动程序）。

> `requirements.txt` 中：`PySide6-Essentials` 与 `pyinstaller` 为运行/构建依赖；
> `pytest`、`numpy`、`matplotlib` 为**开发/测试依赖**（后者仅用于旧矢量参考实现
> 与数值一致性交叉测试，并**不进入最终 EXE 运行路径**）。

## 14. 重新构建 EXE

使用 `scripts\build_exe.bat` 一键完成：创建虚拟环境 → 安装依赖 → 运行测试
（测试失败即停止）→ 构建并验证 onedir 版本 → 构建 onefile 单文件 EXE
→ 启动/退出/再启动自动验证 → 输出路径、大小与 SHA-256。

```bat
scripts\build_exe.bat
```

## 15. 测试与验证

本项目使用 **pytest** 进行单元测试、GUI 冒烟、Hover 交互与数值稳定性测试，
当前 **1015** 项全部通过：

| 测试文件 | 用例数 | 覆盖内容 |
|----------|-------:|----------|
| `test_llc_model.py` | 233 | FHA 数学模型（增益公式、谐振点、峰值、换算） |
| `test_boundary_rc.py` | 238 | 阻容分界线（Im(Zin)=0）数学与 GUI |
| `test_boundary_frequency_stability.py` | 175 | boundary_frequency 极端数值稳定性 |
| `test_llc_py_crosscheck.py` | 135 | llc_py ↔ llc_model 数值一致性与参考交叉验证 |
| `test_boundary_frequency_monotonic.py` | 57 | 边界频率单调性与趋势 |
| `test_llc_plot.py` | 31 | QPainter 绘图层（对象复用、数据更新） |
| `test_boundary_frequency_reference.py` | 31 | 边界频率高精度参考验证 |
| `test_gui_smoke.py` | 28 | GUI 冒烟（窗口、参数交互、重入保护） |
| `test_ui_interaction.py` | 25 | Hover Inspector / 图例 / Y tick / 分层缓存 |
| `test_boundary_frequency_tricky.py` | 23 | 边界频率边界值（Q=0、极大 K/Q） |
| `test_perf_fix.py` | 20 | 性能增量刷新、事件合并、缓存稳定 |
| `test_boundary_gui.py` | 11 | 阻容边界 GUI 视觉与内容 |
| `test_cjk_font.py` | 8 | 中文字体自动探测 |

> 提示：GUI 测试使用 `QT_QPA_PLATFORM=offscreen`，可在无图形桌面环境运行。

## 16. 技术架构

| 组件 | 用途 | 是否进入最终 EXE |
|------|------|:---:|
| Python | 编程语言 | — |
| PySide6 / Qt | 桌面 GUI 框架（QtCore/QtGui/QtWidgets） | ✅ |
| 纯 Python 数学层（`llc_py.py`） | LLC FHA 计算 | ✅ |
| QWidget + QPainter（`plot_widget.py`） | 绘图与渲染（无 Matplotlib） | ✅ |
| NumPy | 旧矢量参考实现（`llc_model.py`）交叉测试 | ❌ 仅开发/测试 |
| Matplotlib | 参考交叉测试 | ❌ 仅开发/测试 |
| PyInstaller | 构建单文件 / onedir EXE | 构建期 |
| pytest | 自动化测试 | ❌ 仅开发/测试 |

## 17. 适用范围与局限性

- 本工具基于 **FHA 基波近似**，适用于参数趋势分析和教学；
- **不能替代** 开关级时域仿真；
- **不能替代** 器件应力分析、ZVS 范围验证、磁件损耗计算与闭环稳定性验证；
- 实际设计仍需结合仿真与硬件测试；
- 当前发布目标为 Windows 10 / 11 64 位（其他显卡 / VM / RDP 环境以实际机器为准）。

## 18. 项目结构

```
LLC-Gain-Curve-Visualizer/
├─ src/
│  ├─ main.py             PySide6 主窗口与交互逻辑
│  ├─ plot_widget.py      QPainter 绘图层（三层缓存、Hover、图例）
│  ├─ llc_py.py           纯 Python 数学层（增益、阻容边界、峰值）
│  ├─ llc_model.py        矢量参考数学模型（开发/交叉测试）
│  ├─ llc_plot.py         旧 Matplotlib 参考绘图层（仅测试）
│  └─ cjk_font.py         中文字体自动检测
├─ tests/                 1015 项测试
├─ scripts/               构建、测量、验收脚本
├─ docs/
│  ├─ images/             最终界面截图
│  ├─ BUILD_AND_VALIDATION.md
│  └─ release-notes-vX.Y.Z.md
├─ .github/workflows/     CI（Windows 3.10/3.11）
├─ requirements.txt
├─ LICENSE
├─ CITATION.cff
├─ CHANGELOG.md
├─ CONTRIBUTING.md
├─ SECURITY.md
├─ OPTIMIZATION_REPORT.md
├─ UI_INTERACTION_OPTIMIZATION_REPORT.md
└─ THIRD_PARTY_NOTICES.md
```

## 19. 引用方式

```bibtex
@misc{gaincurve2026,
  title  = {LLC Gain Curve Visualizer},
  author = {nobodycareme},
  year   = {2026},
  url    = {https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer},
}
```

详见 [CITATION.cff](CITATION.cff)。

## 20. 贡献指南

欢迎报告问题与提交代码贡献。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 21. License

本项目使用 [MIT License](LICENSE)。

## 22. 致谢

- [Qt for Python (PySide6)](https://doc.qt.io/qtforpython/) — LGPLv3（运行时依赖）
- [PyInstaller](https://pyinstaller.org/) — GPLv2 (with exceptions)（构建依赖）
- [NumPy](https://numpy.org/) — BSD-3-Clause（仅开发/测试参考）
- [Matplotlib](https://matplotlib.org/) — Matplotlib License（仅开发/测试参考）

具体第三方组件与许可证细节见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。