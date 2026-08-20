# Contributing

欢迎为本项目贡献代码、报告问题或改进文档。请先阅读本指南。

## 环境配置

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install -r requirements.txt
```

要求：Windows 10/11 64 位，Python 3.10 ~ 3.12 64 位。

## 运行测试

```powershell
set QT_QPA_PLATFORM=offscreen
.\.venv\Scripts\python.exe -m pytest tests -q
```

- 数学模型改动必须配套新增或更新测试；
- 公式或符号修改必须同时更新 `src/llc_model.py` 文档字符串、
  相关测试断言以及 README/README_EN 中的数学表达式；
- 符号体系唯一约定：`K = Lm/Lr`、`fn = fs/fr`、`Q = sqrt(Lr/Cr)/Rac`，
  不允许重新引入 `Ln` 或 `K = fs/fr` 的旧式定义。

## 提交 Issue

- 请在 [Issues](https://github.com/nobodycareme/LLC-Gain-Curve-Visualizer/issues)
  页面新建 Issue，优先使用模板；
- 说明：软件版本、Windows 版本、复现步骤、K/Q/fn/fr 参数与期望/实际结果；
- 如需提交截图，请裁剪后再上传，不要包含本地绝对路径与个人信息；
- 不要在任何公开 Issue 中提交 Token、密码或私人密钥。

## 提交 Pull Request

1. Fork 本仓库并创建功能分支；
2. 保持修改范围最小化；
3. 运行全部测试，确保全部通过（新增用例时总数随之增加）；
4. 更新 CHANGELOG.md；
5. 提交 PR，并在描述中说明改动内容与验证方式。

## 构建与发布

- 单文件 EXE 由 `scripts\build_exe.bat` 构建，发布请走 GitHub Release，不要将 EXE 提交进仓库。