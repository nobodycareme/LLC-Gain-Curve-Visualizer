## 描述

请简要说明本次改动的内容与动机。

## 关联 Issue

- Fixes #（如相关）

## 改动类型

- [ ] Bugfix
- [ ] 新功能
- [ ] 文档
- [ ] 测试
- [ ] 符号体系 / 公式修改（必须配套测试）

## 验证

请说明本地验证结果：

- [ ] 已运行全部测试：`set QT_QPA_PLATFORM=offscreen && .\.venv\Scripts\python.exe -m pytest tests -q`
- [ ] 全部测试通过（当前基线 317 个用例）
- [ ] 未把 EXE 或其他二进制产物加入提交

## 检查清单

- [ ] 符号体系保持 `K = Lm/Lr`、`fn = fs/fr`（未引入 `Ln` 或 `K = fs/fr`）
- [ ] 无本地绝对路径、无敏感信息
- [ ] CHANGELOG.md 已更新