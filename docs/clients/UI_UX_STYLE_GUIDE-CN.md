# UI/UX 风格指南 - CN

Eurogas Nexus Web 与 Windows 客户端 UI 必须遵循本地参考指南 `C:\Users\qqshu\design.md`，并将其解释为专业、地图优先、资源池原生的欧洲天然气交易决策支持工作台。

## 不可协商的视觉规则

- 使用接近 Vercel 的浅色工程产品语言：页面背景 `#fafafa`，面板 `#ffffff`，内嵌面 `#f5f5f5`。
- 使用墨黑 `#171717` 作为主文本和主操作颜色。
- 使用 `#ebebeb` hairline 边框；避免重阴影。卡片只允许细边框和轻微叠加阴影。
- UI 正文使用 Inter/system sans；技术标签、来源标签、短小 eyebrow 使用 ui-monospace。
- 标题使用 sentence case。除短技术 mono 标签外，不使用全大写标题。
- 应用表面圆角为 8px；pill 控件可以使用 full radius。
- 配色必须克制：墨黑、灰阶、链接蓝、预警琥珀、错误红，以及有明确数据语义的地图颜色。
- 不使用装饰性光斑、气泡、图库图片或缩小版渐变。
- 实现 CSS 中 letter spacing 保持 `0`，即使参考视觉中有负字距。

## Eurogas 驾驶舱适配

- 地图始终是主要工作面，不是背景图。
- 顶部栏是产品/搜索/控制栏，不是营销 hero。
- 首页左侧栏只承载资源池上下文、推荐路径控制和缺失合同阻断状态。
- 首页右侧栏只承载决策结果：净 PnL、路线分配阶梯、经济性快照、策略/预警信号。
- 数据源诊断、运行数据库健康、TSO 准入表、容量汇总、费率表、凭据、术语库和 AI 报告必须放在独立页面，不得重新塞回首页左右栏。
- 地图上的 workspace pill 和汉堡图标是唯一导航入口；首页不得恢复重复横向导航。
- 地图资产搜索框仅在 Network 工作区显示。控件在当前页面无实际作用时不得继续显示。
- 非地图工作区使用紧凑、无卡片外框的页面标题带，并提供同一业务分组内的本地页签。运行状态只保留在全局顶部栏，不在标题卡中重复。
- 只挂载当前工作区。非地图页面后方不得继续保留隐藏的地图 canvas、overlay 或可聚焦控件。
- Strategy 使用始终可见的受控纸面运行命令带，并严格分为四个任务视图：监控、经济性、风险与证据、运行历史。累计 PnL 曲线只能来自 PostgreSQL 中已持久化的策略运行；没有历史时必须显示明确空状态，禁止绘制示意性收益曲线。
- Data Sources 严格分为四个任务视图：待处理、目录、接入与认证、基础设施。Runtime 分为就绪检查、数据交付、治理。仅挂载当前视图；紧凑的就绪上下文保持可见，修复动作跳转到真正负责该任务的工作区。
- MapLibre 控件、attribution、图层 chips 和左右栏不能重叠。
- AI/LLM 功能只能表现为决策支持分析和报告生成，不能表现为自主执行。
- 所有可见字符串必须支持英文和简体中文。

## 实现合约

当前 Web 实现应暴露这些结构类名，以便 contract tests 防止回归：

- `cockpit-topbar`
- `workspace-menu`
- `scenario-rail`
- `decision-rail`
- `trade-result-panel`
- `decision-signal-panel`
- `topbar-search`
- `workspace-page-tabs`
- `workspace-topbar-page`
- `strategy-command-deck`
- `strategy-view-tabs`
- `strategy-performance-chart`
- `source-view-tabs`
- `source-readiness-strip`
- `runtime-view-tabs`
- `runtime-operations-strip`

2026-08-31 的 Image Gen 2 市场工作区视觉方向保存在
`docs/design/references/market-workspace-imagegen-2026-08-31.png`。该文件仅作为设计参考，不是行情数据，也不定义功能需求。

2026-08-31 的 Strategy 工作区参考保存在
`docs/design/references/strategy-workspace-imagegen-2026-08-31.png`。其中曲线和数值仅是视觉设计材料；生产曲线只能使用 PostgreSQL 已持久化的策略运行。

2026-09-01 的 Operations 工作区参考保存在
`docs/design/references/operations-source-center-imagegen-2026-09-01.png`。
其中数据源名称、数量、状态和数值仅是视觉设计材料；生产态势只能来自以 PostgreSQL 为运行事实源的 API。

未来客户端工作如需改变 UI 语言或布局模型，必须先更新本指南。
