# 山东定额助手 · Design System

**Version:** 0.9.1
**Product:** Windows AI 套价辅助工具
**Design dials:** variance 5/10 · motion 3/10 · density 5/10

## Product principle

界面只服务一条主路径：**描述施工内容 → 看推荐方案 → 补关键条件 → 按需查看依据**。

- 一个页面只突出一个主要操作。
- 结论先于资料，推荐先于候选。
- 默认收起专业细节，用渐进展开照顾新手。
- 不依赖装饰制造“高级感”，用排版、留白、节奏和准确文案建立可信度。

## Visual language

- 中性灰绿背景，不用纯白、荧光色、AI 紫色渐变或发光。
- 表面层级只使用背景差、1px 淡边框和极轻分隔；避免厚重阴影。
- 圆角控制在 5/8/10/12px，不使用大胶囊容器。
- 单列内容最大宽度 820px；长文保持约 60–70 个字符的阅读宽度。
- SVG 图标统一为线性、相同描边，不用 emoji 充当控件图标。

## Color tokens

### Light

| Token | Value | Use |
|---|---:|---|
| background | `#F3F4F1` | 主画布 |
| sidebar | `#E9EBE7` | 侧栏 |
| sidebar border | `#D2D5CF` | 侧栏与工作区分隔 |
| surface | `#FAFAF8` | 分组表面 |
| elevated | `#FFFFFF` | 输入框、按钮、弹层 |
| border | `#DADDD7` | 结构分隔 |
| text | `#272A27` | 主文本 |
| secondary | `#5B605B` | 正文辅助 |
| muted | `#7B817A` | 元信息 |
| accent | `#5F6D60` | 稀缺强调色 |
| focus | `#657765` | 键盘焦点 |

### Dark

| Token | Value |
|---|---:|
| background | `#1C1E1B` |
| sidebar | `#161815` |
| sidebar border | `#343834` |
| surface | `#232622` |
| elevated | `#292C28` |
| border | `#393E39` |
| text | `#ECEFEA` |
| secondary | `#BCC2BC` |
| muted | `#8F9790` |
| accent | `#AAB7A8` |

## Typography

- 正文与控件使用 **思源黑体**，标题使用 **思源宋体**；编码使用 Consolas 保持稳定对齐。
- Caption 12px / Meta 13px / Body 15px / Section 17px / Title 22px。
- 正文行高优先可读；标题使用 semibold，不用夸张超大字或全大写。
- 编码、数量、版本保持稳定对齐；辅助文字不能低于 12px。

## Spacing and shape

- 4/8px 基础节奏：4, 8, 12, 16, 20, 24, 32, 40。
- Control height: 40px；compact control: 32px。
- Radius: 3 / 5 / 8 / 10 / 12px；紧凑选择器使用 3px。
- Sidebar: 252px；content max width: 820px。

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

- AI 完成后只保留一个最终结论面；本地候选保存在会话数据中，不与 AI 结果重复堆叠。
- 默认先显示结论、清单编号、定额编号、名称、单位和匹配依据；专业明细按需展开。
- 缺关键条件时在最终结论面直接点选；方案通过本地校验后显示“人工确认”，确认状态写入会话。
- 定额行使用本地工作内容字段生成口语化说明，不由 AI 补写未登记工序。
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
- Ctrl+K 聚焦输入，Ctrl+N 新建分析，Enter 提交，Shift+Enter 换行。

## Accessibility and release checklist

- 正文对比度 ≥ 4.5:1，状态不只依赖颜色。
- 所有可交互组件支持键盘焦点，图标按钮有可读提示。
- 125% / 150% / 200% DPI 下不截字、不横向溢出。
- 980×680 最小窗口、1366×768 常用窗口、宽屏均验证。
- 浅色和深色独立检查；滚动、空状态、加载、错误和长结果均实机检查。
