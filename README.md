<div align="center">
  <img src="assets/images/app.ico" width="82" alt="山东定额助手图标">
  <h1>山东定额助手</h1>
  <p>面向山东工程造价工作的 Windows 本地检索与 AI 辅助分析工具</p>

  [![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
  [![Platform](https://img.shields.io/badge/Platform-Windows%2010%2F11-5B6573)](#运行要求)
  [![Tests](https://github.com/loveramarois-byte/shandong-quota-assistant/actions/workflows/tests.yml/badge.svg)](https://github.com/loveramarois-byte/shandong-quota-assistant/actions/workflows/tests.yml)
  [![License](https://img.shields.io/badge/Code%20License-MIT-2F855A)](LICENSE)
</div>

> [!IMPORTANT]
> 本仓库公开的是应用源码，不含山东定额/清单数据库、PDF 资料、API Key、安装包或任何第三方计价软件文件。使用者必须自行提供来源合法、结构兼容的本地资料库。

## 为什么做这个项目

工程造价人员经常需要在大量定额、清单和规则说明中快速缩小候选范围。本项目把“本地查找”与“AI 解释”分开：先用可追溯的本地数据检索候选，再由用户决定是否将有限摘要交给 AI 分析。

## 核心能力

- **专业隔离**：建筑、安装、市政、园林按当前选择硬过滤，避免宽泛关键词混入其他专业。
- **本地优先**：SQLite FTS5 全文检索，本地候选不依赖网络或 AI。
- **条件排序**：根据施工方式、土类、深度、材料和部位等条件调整候选顺序。
- **原书证据链**：候选项使用稳定记录 ID 和 `[R#]` 引用，逐条显示 PDF 文件、页码与定位状态，可从 AI 回答直接打开原书页。
- **可选 AI**：支持本机 OpenAI/Anthropic 兼容端点，以及 DeepSeek 和智谱 AI 的 OpenAI 兼容接口。
- **隐私边界**：AI 默认关闭；远程分析需要分别确认施工描述和候选摘要的发送权限。
- **Windows 凭据保护**：API Key 使用 DPAPI 绑定当前 Windows 用户，不写入普通设置文件。
- **现代桌面交互**：CustomTkinter 自定义设计系统、Inter 字体、SVG 图标、浅色/深色主题与非阻塞分析流程。

## 工作流程

```mermaid
flowchart LR
    A["输入施工做法"] --> B["选择版本与专业"]
    B --> C["本地 FTS5 检索"]
    C --> D["清单 / 定额 / 规则候选"]
    D --> E{"是否启用 AI"}
    E -->|"否"| F["人工复核与导出"]
    E -->|"是"| G["有限摘要发送"]
    G --> H["引用与编号校验"]
    H --> F
```

## 运行要求

- Windows 10/11 x64
- Python 3.12
- 一份来源合法、schema 版本为 `3` 的兼容 SQLite 资料库

## 快速开始

```powershell
git clone https://github.com/loveramarois-byte/shandong-quota-assistant.git
cd shandong-quota-assistant
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

将你有权使用的兼容数据库放到 `data\shandong_quota.sqlite`，或指定环境变量：

```powershell
$env:SHANDONG_QUOTA_DB = "D:\path\to\authorized-catalog.sqlite"
.\.venv\Scripts\python.exe .\run.py
```

数据库对象要求见 [data/README.md](data/README.md)，manifest 格式参考 [catalog-baseline.example.json](manifests/catalog-baseline.example.json)。

## AI 配置

设置页的普通用户流程是：

1. 选择服务商或本机兼容端点。
2. 输入自己的 API Key（本机端点通常不需要）。
3. 获取模型、选择模型并测试连接。
4. 阅读数据发送范围，再显式启用 AI。

本项目通过标准 HTTP 接口连接可选服务，**不捆绑相关桌面软件、SDK、账号或密钥**。任何服务商名称仅用于说明兼容性，不表示官方关联、授权或背书。

## 项目结构

```text
app/                 应用窗口与主流程
components/          自定义 Design System 组件
controllers/         分析任务状态与取消逻辑
themes/              浅色/深色 design tokens
utils/               检索、AI、凭据、会话与资源工具
assets/              字体、图标、动画和应用图标
tests/               单元与数据库集成测试
packaging/           Windows 安装包配置
data/                仅保留接入说明，不跟踪真实资料
```

## 测试

不需要定额数据库的代码测试：

```powershell
.\.venv\Scripts\python.exe -m unittest `
  tests.test_ai_providers tests.test_analysis_state tests.test_ccswitch `
  tests.test_design_system tests.test_formatting tests.test_layout `
  tests.test_message_format tests.test_query_parse tests.test_scroll `
  tests.test_secrets tests.test_sessions tests.test_settings_dialog_logic `
  tests.test_smoke -v
```

配置兼容资料库后，运行全量集成测试：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 安全与隐私

- 不要将 API Key、项目描述、日志或数据库上传到 Issue。
- 远程 AI 端点只允许 HTTPS；HTTP 仅允许回环地址。
- 详细数据流见 [本地数据与 AI 外发边界](docs/DATA_PRIVACY.md)。
- 漏洞报告方式见 [SECURITY.md](SECURITY.md)。

## 法律与商标边界

- MIT 许可证仅适用于本仓库的原创代码，见 [LICENSE](LICENSE)。
- 定额、清单、PDF、人材机价格和其他专业资料不由 MIT 许可证覆盖。
- “山东定额助手”是本开源项目名称，与政府部门、定额出版单位、AI 服务商或商业计价软件无官方关联。
- 用户应核实当地有效版本、合同约定和项目特征；软件输出是候选与辅助解释，不代替造价专业人员审核。

更完整的资料权利与使用边界见 [docs/LEGAL_AND_DATA.md](docs/LEGAL_AND_DATA.md)。

## 贡献

欢迎提交问题和改进。请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，并确保提交内容不含受限资料、密钥或其他软件文件。

## 许可证

项目原创代码使用 [MIT License](LICENSE)。第三方字体和依赖仍适用各自许可条款，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
