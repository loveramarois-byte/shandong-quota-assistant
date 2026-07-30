# 无版权演示资料库

此目录只保存说明，不提交生成的 SQLite 文件。运行以下命令可生成完全合成的 schema v3 资料库：

```powershell
.\.venv\Scripts\python.exe -m tools.build_demo_catalog
.\.venv\Scripts\python.exe .\run.py --demo
```

可尝试输入：

- `演示基础构件浇筑`
- `演示低压线管敷设`
- `演示园区路基铺筑`
- `演示庭院苗木栽植`

所有名称、编号、关联和说明均为项目自行生成的虚构数据，不对应真实定额、清单、价格或出版物，只用于验证检索、专业隔离、版本隔离、关联、AI 校验和导出流程。
