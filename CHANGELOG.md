# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 的思路编写。

## [v1.0.0] - 2026-08-06

首个正式发布。

### 新增

- LLC FHA（基波近似）增益曲线计算：`M(fn, K, Q)`；
- K = Lm/Lr、Q、fn = fs/fr 实时交互控制；
- 多条固定参考 Q 曲线（Q = 0.1 ~ 10）；
- 并联谐振点 `fnp` 与串联谐振点 `fnr = 1` 标记；
- 当前增益峰值搜索与实时频率换算；
- Windows x64 单文件 EXE（PyInstaller 打包）；
- 数学模型的增量刷新优化与滑块事件合并。

### 修正

- 符号体系统一为 `K = Lm/Lr`（电感比）与 `fn = fs/fr`（归一化频率），
  与旧版 MATLAB 原版 `Ln = Lm/Lr`、`K = fs/fr` 相反，已在资料中全面纠正。

### 优化

- 拖动实时刷新，图形对象复用，无内存/对象增长；
- 界面布局与中文显示字体自动探测。