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

未来客户端工作如需改变 UI 语言或布局模型，必须先更新本指南。
