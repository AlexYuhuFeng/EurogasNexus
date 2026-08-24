# 下一步开发队列

英文主文档：[NEXT_DEVELOPMENT_QUEUE.md](NEXT_DEVELOPMENT_QUEUE.md)

## 队列规则

按顺序执行第一个 `pending` 增量。每个增量必须先有 ExecPlan、测试、中英文运营文档以及真实的 `PARTIAL`/`BLOCKED` 状态。不得为了可见的客户端功能跳过数据库、数据来源追踪、权限或人工复核边界。

## 当前基线

状态：`complete-in-current-worktree`

- PostgreSQL/Alembic 数据结构已到 `0023_storage_nomination_masters`。
- 稳定公共 `/api`，以及受配置限制的 `/api/internal`、`/api/dev`。
- Python SDK、CLI、React/Vite Web 和 Tauri Windows/Linux 客户端。
- 地图资源池、市场、管容、合同、策略、复核、市场定位、数据源、术语库、运行状态、设置和手册工作区。
- Server、Client、AllInOne 部署角色。
- Web、Windows x64、Linux x64/ARM64、部署包和多架构 API 镜像自动发布。

## 已交付增量

- **R22-R28**：客户端拆分、数据边界、来源形态的 PostgreSQL 仿真价格、市场/管容/数据源页面、合同持久化和发布加固。
- **R29**：部署角色、私网预览限制、客户端 API 配置、运行容器和公共数据定时抓取。
- **R30**：正确的残量网络天然气流优化、储气/提名输入校验、统一优化 API 信封、优化测试门禁和 Linux ARM 发布重试。
- **R30A**：把 `App.tsx` 缩减为组合入口，建立 hooks、model、shell 和 workspace renderer 的明确职责，更新模块 owner 测试和中英文 Web 架构规范。该维护增量不改变 R31 的数据库组合优化范围。
- **R30B**：完成标准化 L1 报价和公司 TSO access 数据表、后端路径净价差扫描、不可变决策快照、明确过期状态、稳定 API/SDK 读取，以及 Network/Market 页面每 10 秒刷新的紧凑决策信息流。模拟供应商与未来持牌适配器使用同一数据库合同；该路径级信息流不替代 R31 的组合分配范围。
- **R30C**：完成 PostgreSQL 告警生命周期、10 秒监控 worker、顶部可见告警中心、确认操作、逐告警 DeepSeek 对话、加密凭据、实时连接诊断和真实 DeepSeek 运行时调用。事实与触发条件仍由确定性引擎负责，大模型只解释持久化证据且不能执行任何业务动作。
- **R30D**：策略影子运行持久化与正确性收尾。完成 DB 支撑的影子运行持久化（`strategy_runs`、`strategy_allocation_targets`）、只读运行历史与累计汇总端点、累计纸面盈亏/胜率/最大回撤聚合、累计止损口径、诚实的 `PARTIAL` 候选动作、legacy `elapsed_days` 语义、SDK/CLI 方法，以及 Web 风控可编辑、运行历史和累计绩效展示。
- **ONT-M1**：类型化领域本体与约束收敛。落地严谨、类型化的领域本体（`src/eurogas_nexus/domain/ontology/`）作为唯一语义结构契约：受控词表枚举、动作分类（含禁止动作边界）、类型化概念/关系、可计算约束注册表（委托 `domain/constraints/`）。将散落的 L5 约束（TSO 准入、净回值、止损、分配拆分）与 route-cost/strategy 枚举收敛到单一 home，`business_logic_ontology()` 改为由本体派生，glossary 降级为展示层，并下线孤儿表 `business_ontology_terms`（迁移 `0016`）。

### R31：PostgreSQL 驱动的组合网络优化

状态：`complete-in-current-worktree`

ExecPlan：`.agent/plans/V1_R31_DB_PORTFOLIO_NETWORK_EXECPLAN.md`

已交付 `POST /api/optimization/portfolio-network` 与 SDK 方法
`optimize_portfolio_network`。端点只接受决策元数据，从 PostgreSQL 组装上游
合同、参考节点、有效路由候选、TSO 权限、生效费率、市场观测和 as-of FX，
然后运行共享管容残量网络流模型；最终流量会被分解为“来源→销售”路径并给出
合同级 PnL 归因。每次运行都会把组装输入、来源追踪、假设、阻断项和来源 ID
写入 `optimization_runs`。缺失、过期或不兼容事实一律 fail-closed。

必须完成：

- 从 PostgreSQL 读取上游合同和资源；
- 从 PostgreSQL 市场观测生成销售选项；
- 按 gas day 和产品连接路径拓扑、方向管容、TSO 权限和有效费率；
- 先利用有限的低成本路径容量，再把剩余资源与绕行路径、本地销售和其他市场统一比较；
- 保存来源 ID、观测时间、时效、质量、假设、阻断项和合同级 PnL 归因；
- 数据组装合同确定后再增加 API DTO 和 SDK 方法；
- 所有输出仍需交易员复核，且不可执行。

验收要求：客户端提供的几何、费率和管容不得成为权威数据；缺失、过期或不兼容信息必须明确阻断或警告；跨资源共享管容和 TSO 权限必须生效。

## R32：身份认证、授权、审计和导出治理

状态：`partial-in-current-worktree`

ExecPlan：`.agent/plans/V1_R32_IDENTITY_AUTH_GOVERNANCE_EXECPLAN.md`

已交付：本地 PostgreSQL 身份模型（`identity_principals`、
`identity_api_keys`，迁移 `0022`），USER/SERVICE 主体、哈希 bearer key 和
VIEWER/ANALYST/OPERATOR/ADMIN 角色；release 配置按角色授权（READ/PUBLIC
VIEWER+，GOVERNED ANALYST+，OPERATOR OPERATOR+）；按身份执行商业数据 scope
与未知来源 fail-closed，并在市场观测/报价表面做行级过滤；internal 身份/密钥
管理与受限审计导出，审计保留默认 365 天、先 dry-run。R32A 交付 OIDC
access-token 校验：惰性 HTTPS discovery/JWKS、RS256 验签与
iss/aud/exp 校验、角色与 entitlement 声明映射，无新增 Python 依赖。

剩余：OIDC 交互式登录（redirect/PKCE/refresh/session）与 SAML（若部署需要
浏览器 SSO）；安全验收通过前继续保留私网/VPN-only 部署姿态。

## R33：生产数据源运行

状态：`complete-in-current-worktree`

ExecPlan：`.agent/plans/V1_R33_PRODUCTION_SOURCE_OPERATIONS_EXECPLAN.md`

已交付：`application/source_operations.py` 统一拥有受限指数退避与按来源
新鲜度 SLA；`run_public_ingestion_worker.py` 支持 `--retry-max` /
`--retry-backoff-seconds`，失败后监督循环继续。部署调度器仍由运营方
（systemd/Kubernetes/Windows 任务）负责；商业 provider 仍受凭据、
entitlement 与 provider certification 门控。

## R34：网络流、储气和提名客户端工作流

状态：`complete-in-current-worktree`

ExecPlan：`.agent/plans/V1_R34_STORAGE_NOMINATION_CLIENT_WORKFLOWS_EXECPLAN.md`
与 `.agent/plans/V1_R34A_STORAGE_NOMINATION_RUNTIME_SECURITY_ACCEPTANCE_EXECPLAN.md`

已交付：`POST /api/optimization/storage-dispatch` 与
`POST /api/optimization/nomination-window` 及 SDK 方法。SANDBOX_SCENARIO
支持显式评估输入；RUNTIME_DECISION 从 PostgreSQL 组装储气设施/库存/市场/FX
事实与提名窗口 master（迁移 `0023`，三张表），并拒绝客户端设施/窗口事实。
提名只返回接受/调整量，不存在提交动作。自动化安全验收证据可由
`scripts/security/run_security_acceptance.py` 生成；在移除私网/VPN-only
姿态前仍需真实部署的外部验收。
