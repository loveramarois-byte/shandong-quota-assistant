# 山东定额助手 · Design System

**Version:** 0.8.13
**Product:** Windows AI 套价辅助工具
**Design dials:** variance 2/10 · motion 2/10 · density 3/10

## Product principle

界面只服务一条主路径：**描述施工内容 → 看推荐方案 → 补关键条件 → 按需查看依据**。

- 一个页面只突出一个主要操作。
- 结论先于资料，推荐先于候选。
- 默认收起专业细节，用渐进展开照顾新手。
- 不依赖装饰制造“高级感”，用排版、留白、节奏和准确文案建立可信度。

## Visual language

- 暖中性背景，不用纯白、荧光色、AI 紫色渐变或发光。
- 表面层级只使用背景差、1px 淡边框和极轻分隔；避免厚重阴影。
- 圆角控制在 5/8/10/12px，不使用大胶囊容器。
- 单列内容最大宽度 860px；长文保持约 60–70 个字符的阅读宽度。
- SVG 图标统一为线性、相同描边，不用 emoji 充当控件图标。

## Color tokens

### Light

| Token | Value | Use |
|---|---:|---|
| background | `#F7F6F2` | 主画布 |
| sidebar | `#EFEDE7` | 侧栏 |
| sidebar border | `#C8C4BC` | 侧栏与工作区分隔 |
| surface | `#F2F0EA` | 分组表面 |
| elevated | `#FCFBF8` | 输入框、按钮、弹层 |
| border | `#DEDBD3` | 结构分隔 |
| text | `#292824` | 主文本 |
| secondary | `#5F5C55` | 正文辅助 |
| muted | `#817D74` | 元信息 |
| accent | `#5C6557` | 稀缺强调色 |
| focus | `#737E6C` | 键盘焦点 |

### Dark

| Token | Value |
|---|---:|
| background | `#1E1D1A` |
| sidebar | `#181714` |
| sidebar border | `#4A463E` |
| surface | `#25231F` |
| elevated | `#2B2924` |
| border | `#3D3A34` |
| text | `#EFEEE9` |
| secondary | `#C7C3BA` |
| muted | `#969087` |
| accent | `#B7BDAA` |

## Typography

- UI font: **Inter** Regular / Medium / SemiBold / Bold，中文由 Windows 系统字体回退。
- Caption 12px / Meta 13px / Body 15px / Section 17px / Title 22px。
- 正文行高优先可读；标题使用 semibold，不用夸张超大字或全大写。
- 编码、数量、版本保持稳定对齐；辅助文字不能低于 12px。

## Spacing and shape

- 4/8px 基础节奏：4, 8, 12, 16, 20, 24, 32, 40。
- Control height: 40px；compact control: 32px。
- Radius: 3 / 5 / 8 / 10 / 12px；紧凑选择器使用 3px。
- Sidebar: 232px；content max width: 860px。

## Core components

### Welcome prompt

- 一句任务标题、一句说明、三个真实示例。
- 示例只填入输入框，不直接提交。
- 用户开始分析后立即移除，不与结果抢占空间。

### Composer

- 常驻内容只有“补充条件”、文本输入和“分析”。
- AI 连接状态由顶部统一表达，不改变提交按钮名称。
- focus / error 使用边框反馈，不改变组件尺寸。

### Result

- 默认只显示：推荐方案、关键待补条件、复制、查看依据。
- 清单和主定额在同一视觉组内；增补项弱一级。
- 候选、识别条件、计时、原书和导出位于“依据与候选”展开区。
- 表格与 JSON 导出必须经过显式确认；复制可用于审阅当前推荐。
- 等待状态只有一个卡片：先说明“查本地资料”，再原地更新为“AI 复核”，不反复插入或移动组件。
- 反馈条用 2px 语义色标记：信息为强调色、提醒为警示色、错误为危险色；狭窄宽度下操作自动换行。

### Sidebar

- 仅保留品牌、新分析、历史记录、资料库状态、设置与关于。
- 侧栏不展示三组大数字；详细统计放在“关于”。

## Interaction and motion

- hover / active / focus / disabled / loading / error 状态齐全。
- 过渡 150–300ms；仅使用颜色、透明度和轻微变换。
- 滚轮输入合并到 8ms 帧内；嵌套滚动到边缘时交给父容器。
- 尊重 Windows 减少动画偏好；加载动画仅用于等待状态。
- Ctrl+K 聚焦输入，Ctrl+Enter 提交，Esc 关闭弹层。

## Accessibility and release checklist

- 正文对比度 ≥ 4.5:1，状态不只依赖颜色。
- 所有可交互组件支持键盘焦点，图标按钮有可读提示。
- 125% / 150% / 200% DPI 下不截字、不横向溢出。
- 980×680 最小窗口、1366×768 常用窗口、宽屏均验证。
- 浅色和深色独立检查；滚动、空状态、加载、错误和长结果均实机检查。
