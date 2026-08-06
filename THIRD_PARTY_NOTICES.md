# Third-Party Notices

本项目（LLC Gain Curve Visualizer）基于以下第三方开源组件构建。
各组件的许可由其各自的版权方所有，本项目不声明这些组件的所有权。

注：下列版本为本地验证环境（Windows 10/11 64 位）中实际使用的版本，
具体依赖区间见 `requirements.txt`。

| 组件 | 版本（本次验证环境） | 许可证 | 用途 |
|------|--------------------|--------|------|
| Python | 3.10.11 | PSF License | 运行时 |
| NumPy | 2.2.6 | BSD-3-Clause | 数值计算 |
| Matplotlib | 3.10.9 | Matplotlib License（BSD 风格） | 绘图渲染 |
| Qt for Python (PySide6 Essentials) | 6.11.1 | LGPLv3 | 桌面 GUI 框架 |
| PyInstaller | 6.21.0 | GPLv2（含例外条款） | 构建单文件 EXE |
| pytest | 9.1.1 | MIT | 自动化测试 |
| contourpy | 1.3.2 | BSD-3-Clause | Matplotlib 依赖 |
| kiwisolver | 1.5.0 | BSD-3-Clause | Matplotlib 依赖 |
| pillow | 12.3.0 | HPND | Matplotlib 依赖 |
| python-dateutil | 2.9.0.post0 | BSD-3-Clause (Apache 2.0) | Matplotlib 依赖 |
| pyparsing | 3.3.2 | MIT | Matplotlib 依赖 |

## 许可证说明与再分发提示

- **Qt / PySide6（LGPLv3）**：本程序是动态链接 Qt 库的桌面应用，可按 LGPLv3 以
  二进制形式再分发，同时需满足 LGPL 关于反向工程/再链接的要求。若向终端用户
  分发包含 LGPL 组件的成品，建议随附 LGPLv3 文本及所在组件的版权声明。
- **PyInstaller（GPLv2 带例外）**：使用 PyInstaller 构建的独立程序不视为衍生作品；
  但 PyInstaller 自身的许可证为 GPLv2 with exceptions。
- 本仓库不随附上述组件的完整源码/许可证文本，具体文本请从各组件官方发布处获取。

## 免责声明

第 3-party 许可证信息基于公开元数据整理，如与组件实际发布文本不一致，以组件
官方文本为准。本说明不构成法律意见。