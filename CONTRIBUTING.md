# 贡献指南

感谢你愿意改进山东定额助手。

## 开发流程

1. Fork 仓库并从 `main` 创建短期分支。
2. 保持修改聚焦，不要在同一个 PR 混入无关重构。
3. 为行为变更增加或更新测试。
4. 运行代码编译检查和相关测试。
5. 在 PR 中说明问题、解决方式、验证结果和数据边界。

## 数据与密钥红线

提交内容不得包含：

- 定额、清单、PDF、人材机价格或其数据库导出。
- API Key、token、账号密码、DPAPI 密文或 `.env` 文件。
- 用户工程描述、会话、日志、诊断包或个人路径。
- 其他商业软件的可执行文件、数据、图标、截图或反编译产物。

测试数据必须是明确可公开的自建样本，不得从受限资料中抽取。

## 运行检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q run.py app components controllers themes utils tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

全量检索测试需要一份本地兼容资料库。对不涉及检索的改动，可先运行 README 中的无资料库测试集。
