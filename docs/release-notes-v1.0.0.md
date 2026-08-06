# LLC Gain Curve Visualizer v1.0.0

正式版（Latest）| 2026-08-06 | Windows 10/11 64 位

## 功能

- LLC FHA（基波近似）增益曲线计算：`M(fn, K, Q)`；
- `K = Lm/Lr`（励磁电感比）实时调节；
- `Q`（品质因数，`sqrt(Lr/Cr)/Rac`）实时调节；
- `fn = fs/fr`（归一化开关频率）工作点实时调节；
- 多条固定参考 Q 曲线（Q = 0.1 ~ 10）；
- 并联谐振点 `fnp` 与串联谐振点 `fnr = 1` 标记；
- 当前工作点与增益峰值；
- 实际频率换算（`fs = fn · fr`）；
- Windows x64 单文件程序，无需安装 Python / MATLAB。

## 下载

资产名称：`LLC-Gain-Curve-Visualizer-v1.0.0-Windows-x64.exe`

## 系统要求

- Windows 10 64 位；
- Windows 11 64 位；
- 不需要安装 MATLAB；
- 不需要安装 MATLAB Runtime；
- 不需要安装 Python。

## 完整性校验（SHA-256）

```
04DB3032D0820783EA1AE212C2D7BCDD7C259995439856E882597BB82A3398BB
```

`SHA256SUMS.txt` 附件中记录相同值，可同时校验。

## 已验证项目

- 测试：317 项全部通过（`317 passed in 35.11s`）；
- EXE 启动验证：正常启动，窗口标题为「LLC 谐振变换器交互式多增益曲线」；
- 关闭验证：正常关闭，进程退出干净、无残留；
- 重复启动验证：可重复启动运行；
- 界面功能：K/Q/fn 滑块、fr 与纵轴上限、谐振点与峰值标记均验证可交互。

## 已知限制

- 本工具基于 FHA 基波近似，适合参数趋势分析与教学，不能替代开关级时域仿真、
  器件应力、ZVS 范围、磁件损耗与闭环稳定性验证；
- 当前支持 Windows 10 / 11 64 位；
- EXE 未经代码签名，Windows SmartScreen 可能提示“未知发布者”；
- 单文件模式首次启动需要解包，速度略慢。