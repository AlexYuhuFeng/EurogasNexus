# UI/UX 风格指南 - CN

> 本文是已接受的 [`PROFESSIONAL_UI_CONSTITUTION.md`](PROFESSIONAL_UI_CONSTITUTION.md)
> 的中文非规范实现配套文档，该 Constitution 通过 RFC-0001 于 2026-09-08
> 采用。 [`MOTION_SYSTEM.md`](MOTION_SYSTEM.md) 从属于 Constitution，
> [`UI_CONTENT_STANDARDS.md`](UI_CONTENT_STANDARDS.md) 继续负责内容、领域、时间基准、
> 权利和不执行规则；本文没有独立权威。

Eurogas Nexus Web 与 Windows 客户端 UI 遵循专业的欧洲能源分析工作台方向，其中 Network 工作区采用地图优先布局。

## 不可协商的视觉规则

- 当前中性配色仅作为迁移参考：页面背景 `#fafafa`、面板 `#ffffff`、内嵌面
  `#f5f5f5`、墨黑 `#171717` 和 hairline 边框 `#ebebeb`。实现中的 feature
  CSS MUST 使用语义 token，不得散落使用原始颜色。
- 避免装饰性和重阴影。优先使用语义化面和边框，不使用装饰性层叠阴影。
- UI 正文使用 Inter/system sans；技术标签、来源标签、短小 eyebrow 使用 ui-monospace。
- 标题使用 sentence case。除短技术 mono 标签外，不使用全大写标题。
- Constitution 规定固定字号 `11/12/13/14/18/20px`、间距
  `4/8/12/16/24/32px`、控件高度 `28/32/36px`、圆角 `4/6/8px`。
- RFC 采用后不得使用装饰性 pill、巨型工作区标题或任意局部字号、间距、控件高度、圆角。
- 配色必须克制：墨黑、灰阶、链接蓝、预警琥珀、错误红，以及有明确数据语义的地图颜色。
- 不使用装饰性光斑、气泡、图库图片或缩小版渐变。
- 实现 CSS 中 letter spacing 保持 `0`，即使参考视觉中有负字距。

## Eurogas 驾驶舱适配

- Network 工作区采用地图优先布局。Market quotes、Strategy 及其他分析工作区
  根据任务使用主要表格、图表、编辑器或报告工作面。
- 顶部栏是产品/搜索/控制栏，不是营销 hero。
- 首页左侧栏只承载资源池上下文、推荐路径控制和缺失合同阻断状态。
- 首页右侧栏只承载决策结果：净 PnL、路线分配阶梯、经济性快照、策略/预警信号。
- 数据源诊断、运行数据库健康、TSO 准入表、容量汇总、费率表、凭据、术语库和 AI 报告必须放在独立页面，不得重新塞回首页左右栏。
- 共享 shell 负责五个一级工作区；不得增加竞争性的导航模型或装饰性 pill 触发器。
  地图局部控件仍归地图局部使用。
- 共享 shell 统一负责 gas day、delivery product、适用时的 Portfolio、主要市场上下文和运行/数据状态。
  页面内部不得重复全局上下文选择器。
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
- `workspace-primary-tabs`
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

未来客户端工作如需改变 UI 语言或布局模型，必须先更新 `UI_CONTENT_STANDARDS.md`，再同步更新本文与 EN 配套文档。
