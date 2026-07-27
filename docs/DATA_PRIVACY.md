# 本地数据与 AI 外发边界

本文档说明开源客户端当前实现的数据流和安全边界。使用者或二次发布者应根据自身组织、地区和数据类型补充适用的隐私政策。

## 数据流

- 本地检索：施工描述在本机查询只读 SQLite；不需要 AI。
- AI 辅助：只有用户在设置中同时确认“施工描述发送权限”和“本地资料摘要发送权限”后才启用。
- 发送字段：施工描述、所选定额版本、清单依据、专业、结构化条件和本轮候选摘要。
- 不发送：完整 SQLite、会话文件、日志、其他历史查询和本机文件路径。
- 端点：远程只允许 HTTPS；HTTP 只允许 `127.0.0.1`、`localhost` 或 `::1`。
- 连接测试：只发送固定英文 `OK` 探针，不发送工程描述或本地资料。
- 模型列表：点击“获取模型”时只向所选服务商调用 `/models`，不发送工程描述、本地资料或历史记录。
- 服务商：可选择本机 ccSwitch、DeepSeek 或智谱 AI；远程服务的数据处理规则由对应服务商和用户账号协议决定。

## 本地存储

- 设置：`%APPDATA%\ShandongQuotaAssistant\settings.json`
- API 凭据：`%APPDATA%\ShandongQuotaAssistant\credentials.json`
- 会话：`%APPDATA%\ShandongQuotaAssistant\sessions\`
- 日志：`%APPDATA%\ShandongQuotaAssistant\logs\`
- 导出：`%APPDATA%\ShandongQuotaAssistant\exports\`

会话 V2 按 `turn_id` 保存查询、筛选口径、候选快照 hash、AI 尝试、校验和人工暂存项。文件采用临时文件 + `fsync` + 原子替换；上一版保留为 `.bak`。删除记录先写 tombstone，再移到本地 `sessions\trash\`，迟到任务不能复活原记录。

API Key 按服务商分别保存，并使用 Windows DPAPI 绑定当前 Windows 用户加密。`settings.json` 不保存 Key 明文；`credentials.json` 中只有 `dpapi:` 密文。复制程序目录不会复制凭据，其他 Windows 用户也不能直接解密当前用户的凭据。

## Windows 用户边界

当前存储依赖 Windows 用户配置目录的访问控制。应用没有自行加密会话；同一 Windows 账户下运行的进程、管理员、终端安全软件和备份软件可能读取这些文件。处理敏感项目时，应使用受控 Windows 账户、磁盘加密和组织批准的备份策略。

应用使用命名互斥体限制为单实例，避免多个进程同时覆盖会话。该机制不是权限隔离或加密。

## 日志与错误

- 应用日志不记录施工描述、AI 响应正文、API token 或 URL query。
- HTTP 上游错误正文不会进入异常和日志。
- AI 地址禁止内嵌账号、密码、query token 或 fragment。
- 诊断包只包含版本、数据库位置、最近会话的 ID/标题/时间和轮转日志；对外提供前应由用户再次检查和脱敏。

## 保留、删除与备份

应用本身不提供组织级保留策略、集中擦除或加密备份。用户可逐条删除会话；删除项暂存于本地回收区以支持损坏恢复。组织部署时应明确：

1. 默认保留天数和自动清理范围。
2. 一键清除会话、回收区、日志和导出的行为。
3. 企业备份是否包含这些目录及其恢复/擦除流程。
4. 资料权利人是否允许候选原文片段提交第三方模型。
