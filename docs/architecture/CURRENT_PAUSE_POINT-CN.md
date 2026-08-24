# 当前暂停点

英文主文档：[CURRENT_PAUSE_POINT.md](CURRENT_PAUSE_POINT.md)

## 状态

检查日期：2026-07-22

Eurogas Nexus 当前是 `0.5.0` 预览发布版本，已经包含 FastAPI 后端、PostgreSQL 运行数据库、Python SDK、CLI、React/Vite Web 客户端、Tauri Windows/Linux 客户端以及按角色部署工具。

产品定位是欧洲天然气市场情报、优化和决策支持。它不是交易场所、订单路由器、提名提交系统、结算平台、法律咨询工具或 ETRM。

## 已验证基线

```text
alembic_revision: 0023_storage_nomination_masters
required_tables: 45
missing_tables: 0
source: runtime-postgresql

app import ok
84 routes
```

> `len(app.openapi()['paths'])` 是版本无关的端点数；原始 `len(app.routes)` 依赖 FastAPI 版本（FastAPI 0.141.x 的惰性 router 下为 25），不宜作为稳定健康指标。

仓库数据结构 head 和显式迁移的本机测试 PostgreSQL 均为 `0023_storage_nomination_masters`，要求 45 张表。本次没有连接任何生产数据库。

客户端只通过 `/api` 或 SDK 获取 PostgreSQL 中的数据，不直连数据库、不读取后端本地文件，也不直接调用数据提供商。数据源密钥由后端管理，任何读取接口都不得返回明文。

## 当前产品结构

- 公共 API：无版本号的稳定 `/api`。
- 运营接口：`/api/internal`，已实现的端点要求后端内部令牌和主体标识。
- 开发接口：`/api/dev`，受运行配置限制。
- 数据权威来源：PostgreSQL 和 Alembic。
- 客户端：共享的 Web 工作区，以及 Windows x64、Linux x64/ARM64 Tauri 外壳。
- 部署角色：Server、Client-only、AllInOne 三类 Release 产物相互独立。Windows AllInOne NSIS 会在已安装 Docker 的测试电脑上自动部署仅回环可见的 PostgreSQL/API 运行时和桌面 Client。外部安全验收完成前，Server 部署只允许用于私网或 VPN 预览环境。`EUROGAS_NEXUS_DEPLOYMENT_POSTURE` 默认为 `private_network_preview`；只有同时设置 `security_accepted` 和存在的 `EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE` 文件才生效。
- 预览价格：仿真数据源把与真实提供商同形的数据写入 PostgreSQL，并完整经过后端、API、SDK/客户端链路。
- 日内决策：标准化 L1 报价触发后端路径净价差扫描；已持久化机会通过 API/SDK 提供，Network、Market 和 Strategy 工作区每 10 秒读取一次。过期快照不会继续显示为可审阅机会。
- 监控与 DeepSeek：PostgreSQL worker 每 10 秒归一化机会、策略和数据源失败告警；稳定指纹避免同一事件重复产生调用费用。顶部告警中心支持确认和显式 DeepSeek 对话。2026-07-22 已验证一次真实连接、三次告警解释和一次交互回答；自动化测试仍然不访问外网。
- 策略影子运行持久化：每次 `POST /api/strategy-lab/evaluate` 的结果都会写入 `strategy_runs` 和 `strategy_allocation_targets`，并附带 `run_id`、指示性 `paper_pnl_gbp`、累计盈亏和命中标记。只读端点 `GET /api/strategy-lab/runs`、`/runs/{run_id}` 和 `/summary` 聚合累计纸面盈亏、胜率和最大回撤。止损现在按累计（历史 + 本次）盈亏判定，`PARTIAL` 结果返回 `REVIEW_PARTIAL_STRATEGY` 而非正向配置建议。
- 公共数据源摄入可安全重跑：观测记录按自然主键 upsert，`observed_at_utc` 保持首次观测时间；ENTSOG 参考网络只替换 ENTSOG 作用域、且仅在新载荷非空时执行（operator 维护的边和映射绝不被摄入路径删除）；每次运行（无论成败）都追加 `audit_events` 和一条 `ingestion_runs`。过期运行数据按保留策略清理（报价 30 天 / 观测 90 天 / 机会 7 天），入口为 `scripts/ops/prune_runtime_data.py`。
- 后端规范化市场视图：`GET /api/market/normalized` 为每条市场观测返回后端计算的 `hub`、`tenor`、`is_gas_price` 和 `price_gbp_mwh`（最新 ECB 汇率图、最多三跳换算）。前端的 TS 重实现（`marketPriceNormalization.ts`）已删除；Strategy 场景组装与 Market 终端改消费后端规范化行和后端拥有的 `/api/market/spreads`（`from_hub`/`to_hub`/`spread_eur_mwh`），契约测试禁止客户端汇率/价差数学。客户端不本地持久化任何业务数据；复核 actor 仅存在于页面内存（真实身份待 R32）。
- API 契约演化策略：`docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`（`/api` 只增不改、弃用流程显式、无 `/v1` 别名），由钉死 92 条路径的表面稳定性门（`tests/contract/test_api_surface_stability.py`）强制执行——任何路径变更在显式声明前都会让 CI 变红。
- Provider 认证门：licensed 适配器只有在 operator 通过 internal 端点（`POST /api/internal/sources/certification`，带审计事件）写入 `provider_certifications` 证据并通过「模拟→真实」门（stage `live_validated` 且含 `simulated_shape_match` 与 `live_sample_validation` 检查）之后，才能标记为 native live。未认证但有记录的 licensed 源显示为 `active_uncertified`，永远不是 workflow-ready（fail-closed，含 DB 不可用时）。
- 最小 actor 身份模型：`docs/architecture/ACTOR_IDENTITY_MODEL.md` 定义 operator principal（由 `domain/identity/principal.normalize_principal` 统一校验），记录在复核决策、审计事件、internal operator 写入与认证证据上。R32 增加 PostgreSQL 支撑的 USER/SERVICE 身份、哈希 bearer key 与角色授权；公司 SSO/OIDC 推迟到 R32A。
- R32 本地身份治理：PostgreSQL `identity_principals` 与 `identity_api_keys`
  存储 USER/SERVICE 身份和哈希 bearer key。release 配置按
  VIEWER/ANALYST/OPERATOR/ADMIN 角色门控 PUBLIC/READ、GOVERNED 和 OPERATOR
  路由；按身份执行商业数据 scope 并对市场观测/报价行级过滤（fail-closed）；
  internal 身份/密钥管理与审计导出/保留端点按 profile 门控。R32A 增加 OIDC
  access-token 校验（惰性 HTTPS discovery/JWKS、RS256、声明到角色映射），
  无新增依赖。
- 复核工作流 UI：Review 工作区现在展示持久化决策历史，并通过 `GET/POST /api/review/decisions` 记录 `accepted` / `rejected` / `needs_attention` 决策（可附备注）。actor 为显式的页面级输入（默认 `operator`），仅存在于组件内存——客户端不在本地持久化任何业务数据；界面明示 actor 尚未经 SSO 认证（R32）。
- 管线可观测性 UI：Runtime 工作区展示后端管线健康聚合（每源状态/连续失败/最近成功、近 5 分钟报价新鲜度、开放告警、最新机会），数据来自 `GET /api/runtime/pipeline-health`；顶栏显示由 `streamingActive` 驱动的数据模式徽章（SSE 可用时「实时推送」，否则「轮询兜底」）。Sources 工作区展示 provider 认证门（`unverified` / `simulation_matched` / `live_validated` 徽章，`active_uncertified` 关注态及 `certify` 下一动作）。
- PostgreSQL 组合网络优化：`POST /api/optimization/portfolio-network`
  只接受决策元数据，从 PostgreSQL 组装上游合同、参考节点、有效路由候选、
  TSO 权限、生效费率、市场观测和 as-of FX，再调用共享管容残量网络流模型。
  引擎会先用尽低价路径容量，再把剩余气量分流到替代路径、本地销售或其他
  市场，并把来源 ID、时效、质量、假设、阻断项和合同级 PnL 归因写入
  `optimization_runs`。客户端不得向该端点提交网络几何、费率、管容或价格。
- R33 数据源运营：公共摄入 worker 已接入受限指数退避与按来源新鲜度 SLA；
  部署调度器仍归运营方管理。
- R34 储气/提名评估：`POST /api/optimization/storage-dispatch` 与
  `POST /api/optimization/nomination-window` 暴露验证过的引擎并带运行证据。
  SANDBOX_SCENARIO 支持显式输入；RUNTIME_DECISION 从 PostgreSQL 组装储气
  设施/库存/市场/FX 事实与提名窗口 master（迁移 `0023`），并拒绝客户端
  设施/窗口事实；不存在提交动作。
- 类型化领域本体：`src/eurogas_nexus/domain/ontology/` 是唯一的语义结构契约（受控词表枚举、含禁止动作边界的动作分类、类型化概念/关系、可计算约束注册表）。散落的 L5 约束（TSO 准入、净回值、止损、分配拆分）与 route-cost/strategy 枚举已收敛到其中；glossary 为展示层；孤儿表 `business_ontology_terms` 已下线（迁移 `0016`）。

## 当前优化能力

稳定的操作员输入端点：

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
POST /api/optimization/portfolio-network
POST /api/optimization/storage-dispatch
POST /api/optimization/nomination-window
```

前四个端点接受操作员提供的沙箱输入，统一返回 `data/meta` 信封；第五个
端点为纯数据库运行时决策，所有业务输入都从 PostgreSQL 组装，绝不接受
客户端提交的网络几何、费率、管容或价格。共享管容网络流使用带反向弧的
残量网络算法，并校验最终流量、管容、成本和节点流守恒。储气调度和提名
窗口评估仍是已测试的内部原型。

## 发布状态

- 普通 CI 执行 Python、优化器、API 导入和 Web 验证，并在 PR 上构建桌面包。
- 每次 `main` 提交由 Build and Release workflow 构建 Web、Windows Client-only、Windows AllInOne、Linux x64、Linux ARM64、Server 部署包和 amd64/arm64 API 镜像。
- Linux Tauri 依赖安装使用 Ubuntu 官方 HTTPS 镜像和有限重试，降低 ARM runner 的瞬时网络故障影响。

## Web 应用架构

React 的 `App.tsx` 现为九行组合入口，只创建应用 controller 和 shell。工作流
状态位于 `app/hooks`，组合决策派生模型位于 `app/model`，长期存在的界面框架
位于 `app/shell`，页面选择位于 `app/workspaces`。Contract test 会强制保持
入口简洁，并按真实模块 owner 验证功能，不再要求所有实现都出现在
`App.tsx` 文本中。

详见 [WEB_APPLICATION_ARCHITECTURE-CN.md](../clients/WEB_APPLICATION_ARCHITECTURE-CN.md)。

## 尚未完成的正式交付条件

1. OIDC 交互式登录（redirect/PKCE/refresh/session）与 SAML 仍推迟。R32/R32A
   本地身份、角色授权、商业 scope 与审计治理已交付；安全验收通过前服务器
   角色仍只允许私网/VPN 部署。
2. 商业数据源必须由客户提供密钥、授权和许可，并经过运营验证。
3. 公共数据源重试/退避与新鲜度 SLA 已交付（R33）；部署调度器所有权、
   商业 provider 生产运行和生产告警投递渠道仍属部署工作。
4. 组合级优化已从 PostgreSQL 组装合同、路径、费率、管容、TSO 权限和 FX，并完成合同级 PnL 归因；数据源调度、告警投递和导出治理的生产化属于 R33。
5. 储气/提名评估工作流已面向复核开放（R34）；自动化安全验收证据已通过，
   但真实部署的外部验收仍未完成。
6. 订单和 PnL 是只读导入观测；系统不创建、修改、取消、路由或执行订单，也不做交易捕获。

## 下一步

按照 [NEXT_DEVELOPMENT_QUEUE-CN.md](NEXT_DEVELOPMENT_QUEUE-CN.md) 剩余工作
是外部安全验收（渗透测试、OIDC TLS 评审、备份恢复演练、负责人签批），通过后
才可取消私网/VPN-only 姿态。S4.3 的 `/api/workflows/*` 已完成移除。
