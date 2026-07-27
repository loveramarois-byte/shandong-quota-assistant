# 本地资料库接入

此目录在公开仓库中不包含真实定额、清单或 PDF 数据。

## 查找顺序

应用按以下顺序查找 SQLite 资料库：

1. `SHANDONG_QUOTA_DB` 环境变量指定的路径。
2. 应用目录下的 `data/shandong_quota.sqlite`。

## 最低兼容要求

- SQLite `PRAGMA user_version = 3`。
- 必需表或视图：`quota_items`、`bill_items`、`bill_quota_links`、`chunks`。
- 必需 FTS5 虚拟表：`chunks_fts`。
- `discipline` 值应使用 `building`、`installation`、`municipal` 或 `landscape`。
- 定额版本为 `2016`/`2025`，清单依据为 `2013`/`2024`。
- `chunks` 至少提供 `chunk_id`、`chunk_type`、`edition`、`discipline`、`code`、`title`、`source_path`、`pdf_page`、`text`、`metadata_json`。

应用以只读模式打开数据库，并在首次连接时校验 schema 版本与必需对象。

## 权利要求

只接入你有权处理的资料。如需分发安装包，还需要单独确认数据复制和再分发权。请勿将实际数据库、源 PDF 或其摘录提交到公开仓库。
