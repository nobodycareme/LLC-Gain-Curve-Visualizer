# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 的思路编写。

## [v2.0.0] - 2026-08-28

一次重大功能升级：仍以 LLC FHA 多增益曲线分析为核心，新增工程参数辅助设计、
调频范围推导与 FHA 电流/应力估算，并对 UI 做整体现代化重构。

### Added

- **工程参数辅助设计面板**（默认折叠，曲线优先）：Vin_min / Vin_nom / Vin_max、
  Vo、Pout / Io、半桥/全桥拓扑、中心抽头/全桥整流 × 二极管/同步整流、
  自动/手动匝比、η、Vf、过载倍率、手动/推荐 Q；
- **自动计算**：n、RL、Re、Zr、Lr、Lm、Cr；
- **M/fn 工作范围**：M_req_min / M_req_max、Q_full / Q_overload、
  fn_min / fn_max、fs_min / fs_max；
- **FHA 电流与 Cr 应力**：Ioe、Im、Ir、Cr RMS 电流、Cr 峰值电压；
- 工程参数输入采用**字段卡片布局**（FieldPair），整流 ComboBox 宽度按最长文本
  自适应，杜绝文字截断与字段串位；
- **结果侧栏**：可折叠/恢复，恢复按钮常驻窄控制条，Splitter 禁止折到零；
- **显示选项 Popup**：参考 Q / 阻容边界 / M / fn 范围图层的显示控制；
- Q 数字输入框（与滑块双向同步，300ms 防抖）。

### Changed

- **现代化 Windows 11 / Fluent 风格 UI**（统一 QSS：卡片、滑块、下拉框、滚动条）；
- **曲线主导布局**：Header + 左侧曲线 + 右侧结果 + 底部参数调节；
- 工程参数全面中文化，消除"计算模型：FHA"等冗余标签；
- 结果区结构化展示（当前工作点 / 谐振腔参数 / 调频范围 / 电流与应力 / 设计分析 / 建议），
  单一滚动区域；
- 横坐标可读性：主刻度 0.1/0.2/0.5/1/2/5/10，刻度数字与轴标题纵向分离不重叠。

### Fixed

- K 拖动 preview 参考曲线污染（数据隔离，释放后全精度重算）；
- 工作点/曲线几何错位；
- 阻容分界线"看不见但可 Hover"的隐藏曲线（fn>1 不再数学外推参与 Hover）；
- 结果侧栏折叠后无法恢复（恢复按钮随侧栏一起消失）；
- 全屏时右侧结果区空白带（ResultPanel 填满 wrapper，不残留缝隙）；
- 工程参数 16 列 grid 布局串位、ComboBox 文本截断（改 FieldPair + 3 行布局）；
- X 轴刻度显示问题（只到 decade、刻度与轴标题重叠）；
- 输入自动应用时不刷新、滚动位置跳变等交互问题。

### Performance

- K 拖动优化（曲线族预览隔离，避免色带污染）；
- 显示图层 lazy rebuild（隐藏层不参与绘图/Hover/图例）；
- 工程参数与应力计算 throttle 合并，避免高频拖动触发无谓重算；
- QPainter 缓存（Static / Semi-Dynamic / Overlay 三层）。

### Packaging

- 移除错误打包进 EXE 的 Qt 组件、translations、无用插件；
- EXE 由 v1.0.0 约 27.6 MB 减小至当前约 20.85 MB；
- 单文件 EXE + SHA256SUMS.txt 作为正式 Release 资产。

### 兼容性

- 运行符号体系统一不变：`K = Lm/Lr`、`fn = fs/fr`、`Q = sqrt(Lr/Cr)/Rac`；
- 数学核心（增益、阻容边界、fn 求解、应力）未改动，仅做 Hover 有效域修复；
- 1172 项测试通过、8 项跳过、0 失败（含 TI SLUP263 回归与 EXE 打包审计，详见 README）。

---

## [v1.0.0] - 2026-08-20

首个正式发布（GitHub Release 最终版）。

### 新增

- LLC FHA（基波近似）增益曲线计算：`M(fn, K, Q)`；
- **精确阻容分界线**：严格通过 FHA 输入阻抗虚部为零 `Im(Zin) = 0` 计算，
  并明确与增益峰值区别（`Im(Zin)>0` 感性区 / `<0` 容性区）；
- 感性区 / 容性区实时判断；
- **Curve Hover Inspector**：鼠标悬停任意参考 Q 曲线、当前 Q 曲线或阻容分界线，
  实时显示该数学点的 Q / K / fn / M / fs / 工作区域，以及边界的 Mb / Qb；
- 并联谐振点 `fnp` 与串联谐振点 `fnr = 1` 标记、增益峰值、当前工作点；
- K = Lm/Lr、Q、fn = fs/fr 实时交互控制；
- Windows 10/11 x64 单文件 EXE 与极速 onedir 双版本（PyInstaller 打包）。

### 变更

- 绘图后端从 **Matplotlib 迁移至 PySide6 QWidget + QPainter**（纯 Python + Qt 栅格绘制）；
- **NumPy / Matplotlib 移出最终 EXE 运行路径**（仅保留为开发/测试参考与交叉验证依赖）；
- 自适应图例（依据窗口宽度动态列/行数，随 resize 自动重排）；
- 动态规整 Y 轴刻度（nice number 算法）；
- 正确对数横轴次网格（每个十倍频程 2..9，无重复错位）；
- 曲线原生裁剪（保留几何连续，不做断线式过滤）；
- 阻容分界线改为高对比品红粗虚线并在线旁标注；
- 绘图架构拆分为 Static / Semi-Dynamic / Overlay 三层缓存（QPainterPath + QPixmap）。

### 性能

- EXE 体积显著降低（onefile ≈ 26.35 MiB）；
- 启动速度显著提升（onedir 极速版启动更快；onefile 首次需解包但已优化）；
- fn / Q 交互延迟显著降低（fn 拖动 P95 ≈ 3.7 ms，Q 拖动仅重算当前曲线）；
- 滑块释放不再全量重算（消除"松手顿一下"）。

### 修正

- 纠正增益峰值与阻容边界的概念混用；
- 修复 `boundary_frequency` 在极端 K/Q 下的数值稳定性（分支选择 + 防溢出判别式）；
- 修复图例显示不完整、Y 刻度非规整、对数次网格错位、曲线超界断线等问题；
- 修复滑块释放触发全量重算、Hover/重绘性能瓶颈。

### 兼容性

- 运行时符号体系保持 `K = Lm/Lr`、`fn = fs/fr`、`Q = sqrt(Lr/Cr)/Rac`；
- 数学层与绘图层为纯 Python + PySide6，无 numpy/matplotlib 运行时依赖；
- 1015 项自动化测试全部通过（详见 README）。

---

## 变更沿革（最终版收录）

> 以下为从项目演化中沉淀并纳入 v1.0.0 的变更要点，供追溯。

- 符号体系统一为 `K = Lm/Lr` 与 `fn = fs/fr`，全面纠正旧版 `Ln = Lm/Lr`、
  `K = fs/fr` 的相反定义；
- 数学/绘制/GUI 模块严格分层；曲线刷新采用增量更新避免性能退化；
- 测试含语义级断言（如工作点位于曲线上、边界 Im(Zin)=0）。