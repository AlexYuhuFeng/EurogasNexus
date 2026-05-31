# 市场实践对齐审计 - CN

## 目的

本文档用于指导 Claude Code 或其他 CLI Agent 将 Eurogas Nexus V1 的市场、
路线、LNG、资源池、策略、合同和客户端设计继续贴近欧洲天然气交易实践。即使
没有互联网，也应能依照本文档执行当前代码和测试范围内的开发。

## 产品边界

Eurogas Nexus 用于交易员决策支持和策略复核。系统不得下单、路由订单、提交
提名、捕获交易、出具官方审批、替代 ETRM 或提供法律意见。API 和 UI 必须使用
“决策支持”“复核”“候选方案”“信号”“目标”“选项”等表述，不得使用“执行”
“预订”“提名”“官方推荐”等执行性表述。

## DB-First 规则

PostgreSQL 是运行时事实来源。Web、Windows、CLI 和 SDK 客户端只能通过
`/api/v1` 或 Python SDK 访问数据。CSV/JSON 只允许作为模板、公共来源归档、
报告、测试或明确开发 fallback。试用和发布模式不得静默回退到本地文件。

## 路线成本层

- 当前版本只覆盖英国 National Gas NTS。
- 不得将路线成本引擎硬编码为 Easington/Bacton 示例。只要 PostgreSQL 中存在
  已审核的英国 NTS tariff 行，任何英国 NTS entry/exit 点都可计算。
- 支持的业务模式包括虚拟 hub 销售、下游实物交付、beach delivery resource
  销售、储气注入/提取支持，以及输入齐备时的 LNG regas 交付模式。
- 成本栈必须包括入点容量、必要时的出点容量、NTS commodity charge、合同容差
  准备金和提前回收现金价值。
- 路线评估必须考虑公司 TSO access。若公司没有某条路线所需 TSO 的准入，结果
  必须为 blocked 或 partial，并明确给出预警。
- 实时 PnL 对可卖出方案使用 bid mark 进行估值，只输出需要人工复核的决策支持
  信号。

## LNG Regas 层

- 终端准入、货物到港窗口、regas slot、货物大小、send-out capacity、
  storage/holding 约束、定价基础、交付模式和下游实物/虚拟交付要求必须作为显式
  输入。
- 有些 LNG regas 合同要求在入点实物交付，有些不要求。模型必须支持 terminal
  title transfer、virtual hub sale、physical entry delivery 和 downstream
  physical delivery，不能强制所有合同使用同一种模式。
- 跨月 regas 窗口必须拆分为月度 allocation，用于 PnL 和结算复核。
- 有数据时必须展示 terminal capacity source 和 freshness。

## 组合/资源池层

- 客户可能从多个上游合同采购资源，每个合同有不同交付条款、结算滞后、容差、
  成本、容量所有权、TSO access 和可用销售模式。
- 优化必须以 portfolio/resource pool 为单位，将资源分配到兼容销售选项，并计入
  route cost、提前回收现金价值和准入约束。
- 系统可以输出候选 allocation target 和排序信号，但不得执行交易或提交提名。

## 市场价格层

- `MarketObservation` 用于评估价、指数、结算价和派生价格。
- `MarketPriceMark` 或 live mark 用于 ICE OCM、EEX、Trayport、经纪商或其他授权
  来源的实时屏幕报价。
- 卖出方案估值应优先使用可成交或指示性 bid；买入方案估值应使用 ask。
- 每个报价必须包含交易场所、hub、产品、交付窗口、单位、币种、来源、新鲜度、
  质量和授权范围。

## FX 层

- `FxObservation` 必须区分货币对、基准币、报价币、汇率类型、来源和 value date。
- ECB 可作为公共参考汇率来源，但实时抓取必须由操作员明确执行。

## 物理层

- Flow observation 必须包含点位、方向、TSO、国家、周期、来源、新鲜度，以及该值
  是 actual、nomination、allocation 还是 forecast。
- Capacity observation 必须区分 technical、booked、available、firm、
  interruptible、产品期限、方向和预订平台。
- Outage event 必须识别受影响点位/设施、operator、方向、起止时间、状态和容量
  影响。

## 合同/容量层

- 容量合同应尽量使用能量单位 `MWh/day`，不得只依赖 `boe/d`。
- 路线可行性必须包含业务模式、所需容量产品、所需市场报价、所需物理信号、约束
  和置信度。
- 结算滞后、容差、允许出点、overrun 规则和自有容量等合同特定输入必须可由用户
  或操作员配置。

## 策略层

- V1 必须支持策略回测、影子运行和实时监控评估合同。
- 策略例子包括 SAP 对 ICIS Heren 日前价对 ICE OCM、均值回归、评分、最佳时间桶
  和加权组合。
- 策略必须支持可配置时间窗口（例如 15:00-17:00）、bar 大小（例如 5 分钟）、
  资源/资源池选择、风控、单一市场最大数量、止损、数据过期阻断、TSO 准入阻断和
  人工复核预警。
- 策略输出是纸面 allocation target 或决策支持信号，不得成为官方建议、订单、
  提名、容量预订、交易捕获或执行指令。

## 术语表层

- 术语表是后端服务的产品能力，不是静态 UI 文案。
- 必须覆盖机构、交易场所、概念、价格、hub、终端、清算、金融、合同、容量、储气、
  LNG、天气、路线经济性和数据治理术语。
- `/api/v1/glossary` 和 `/api/v1/glossary/{term}` 必须支持 `lang=en`、`lang=zh`
  和 `lang=zh-CN`。
- Python SDK、CLI、Web 和 Windows 客户端都必须能访问术语表。

## 互联网要求

实现当前合约和测试不需要互联网。只有在操作员或 Agent 需要验证最新供应商文档、
API 条款、市场数据许可、依赖版本或官方 TSO 费率 PDF 时，才需要互联网。

## 下一步优先级

1. 扩展 PostgreSQL 迁移，持久化实时市场报价、FX 观测、容量观测、停运事件、策略
   定义、策略运行、策略 allocation target、策略 alert 和术语表。
2. 仅通过脚本写入公共/演示数据，不得提交真实市场数据或客户数据。
3. 增加 API 路由读取 DB 中的市场报价、FX、容量、停运、策略和术语表记录。
4. 客户端使用任何新端点之前，先扩展 SDK DTO。
5. Web 和 Windows 客户端必须采用地图优先交易员驾驶舱；详细价格监控、组合、
   分析、外部订单记录、预警、术语表、用户手册和设置必须分离为标签或窗口。
6. 路线成本保持英国 National Gas NTS 限定，直到后续里程碑加入经审计的欧洲 TSO
   tariff 覆盖和路线优化。
