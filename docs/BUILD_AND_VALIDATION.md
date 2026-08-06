# Build & Validation

本文档是内部构建报告的**公开摘要**，仅包含可对外公开的信息。
工程内部完整报告（含本地路径与机器细节）不随仓库分发。

## 构建环境（验证通过）

| 项 | 值 |
|----|-----|
| 操作系统 | Windows 10/11 64 位 |
| Python | 3.10.11（64 位） |
| NumPy | 2.2.6 / 2.x |
| Matplotlib | 3.10.9 / 3.10.x |
| PySide6-Essentials | 6.11.1（6.7+） |
| PyInstaller | 6.21.0（6.10+） |
| pytest | 9.1.1 |

## 测试

在项目根目录运行：

```powershell
set QT_QPA_PLATFORM=offscreen
.\.venv\Scripts\python.exe -m pytest tests -q
```

最近一次验证结果：

```text
317 passed in 35.11s
```

> 测试使用 `QT_QPA_PLATFORM=offscreen`，可在无图形桌面的环境运行（CI 友好）。

## EXE 构建与验证

使用 `scripts\build_exe.bat` 完成一键构建。脚本内部验证步骤：

1. 定位工程目录（`%~dp0`，相对路径，不依赖绝对安装位置）；
2. 创建 / 复用本地虚拟环境；
3. 安装依赖（离线 wheel 优先，其次在线）；
4. 运行全部测试（失败即终止）；
5. 清理旧构建产物；
6. 构建并启动验证 onedir 版本；
7. 构建 onefile 单文件 EXE；
8. 启动 → 存活检查 → 退出 → 再启动验证；
9. 输出文件大小与 SHA-256。

最终 onefile EXE：`dist\LLC增益曲线.exe`（约 61 MB），
发布用副本使用英文文件名并附带 `SHA256SUMS.txt` 校验文件。

## 已知限制

- EXE 未做代码签名，Windows SmartScreen 可能提示“未知发布者”；
- PyInstaller 单文件模式首次启动需解压，约 5~20 秒；
- FHA 方法为基波近似，适用于趋势分析与教学，不能替代时域/开关级仿真。