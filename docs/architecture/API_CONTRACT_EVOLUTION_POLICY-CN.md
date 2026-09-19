# API 契约演化策略

英文版：[API_CONTRACT_EVOLUTION_POLICY.md](API_CONTRACT_EVOLUTION_POLICY.md)

## 目的

公开 `/api` 表面是五个消费方共享的产品契约：Web、Python SDK、CLI、
Windows/Linux 桌面外壳和双语运营文档。所有消费方都是同一契约的薄客户端，
因此契约只能通过审慎、有测试保障的流程演化。

本文档是契约演化的唯一策略，收敛路线图问题 D（stable unversioned `/api`
无演化策略、五个表面靠自觉同步）。

## 原则

1. **稳定无版本 `/api`。** 公开表面保持无版本 `/api` 前缀；运营与开发路由
   保持受配置门控的 `/api/internal`、`/api/dev` 前缀。任何情况下不提供
   `/v1` 或 `/api/v1` 别名。
2. **默认只增不改。** 新端点和新的可选响应字段是常规演化路径；既有路径、
   参数和字段含义不得静默变更。
3. **破坏性变更是重大事件。** 删除、重命名或改类型任何路径/参数/响应字段，
   必须有书面迁移计划（弃用 → 双轨运行 → 至少跨一个版本后移除）并经
   ExecPlan 评审；不存在原地破坏性变更。
4. **弃用必须显式。** 被弃用的路径或字段须在 OpenAPI 操作上标记
   `deprecated=True`、在运行时信封 `meta.warnings` 中说明，并在本文档弃用表
   登记移除日期；移除前保持可用。
5. **后端是规范化的唯一所有者。** 派生字段（FX 换算、tenor、hub、价差）由
   后端计算，客户端只消费、不得重实现领域逻辑。

## 兼容门

以下测试在契约漂移时让 CI 响亮失败：

| 门 | 文件 | 钉住内容 |
|---|---|---|
| 表面稳定性 | `tests/contract/test_api_surface_stability.py` | 公开路径精确集合；无 `/v1` 别名；仅声明前缀 |
| 文档计数 | `tests/contract/test_architecture_alignment.py` | alembic head、表数、文档化路由数 |
| SDK 对齐 | `tests/contract/test_sdk_backend_parity.py` | SDK DTO 与后端载荷契约 |
| 实时契约 | `tests/contract/test_realtime_contracts.py` | SSE/流式语义；禁 Kafka/Redis 字样 |
| 验证一致性 | `tests/contract/test_validation_consistency.py` | 文档中的规范验证命令 |

## 变更流程

1. 使用 `docs/engineering/EXECPLAN_TEMPLATE.md` 编写公开 ExecPlan，列明
   API 影响与回滚，并更新 ExecPlan 索引；如果变更引入新的规范合同，先
   遵循 `docs/engineering/RFC_PROCESS.md`。
2. 新增路径：同一变更中把路径加入
   `tests/contract/test_api_surface_stability.py` 的
   `PINNED_PUBLIC_PATHS`，并更新文档化路由数（`RELEASE_READINESS.md`、
   `-CN.md` 及 `test_architecture_alignment.py` 断言）。
3. 弃用路径：在 router 标记 `deprecated`、在信封加 warning，并登记到下方
   弃用表。
4. 被拒绝字段：在模型中保持声明，对非空值以稳定 `422` 错误码拒绝并列出每个
   违规字段，登记到上方“被拒绝的请求字段”表，并在同一次变更中从所有客户端
   请求构建器与客户端请求 DTO 中移除。
5. 先补 API、SDK、契约测试，再视为完成。
6. 运行 `CONTRIBUTING.md` 中的完整验证命令集。

## 已声明的新增路径

| 路径 | 声明来源 | 契约 |
|---|---|---|
| `POST /api/optimization/portfolio-network` | 已接受的发布合同 | 仅 DB `RUNTIME_DECISION`；只接受决策元数据，绝不接受客户端网络/费率/管容/价格事实 |
| `POST /api/optimization/storage-dispatch` | 已接受的发布合同 | 仅评估的储气调度；RUNTIME_DECISION 组装 PostgreSQL master/观测 |
| `POST /api/optimization/nomination-window` | 已接受的发布合同 | 仅评估的提名窗口；RUNTIME_DECISION 读取 DB 窗口 master；无提交动作 |
| `GET /api/optimization/nomination-windows` | 交易台时钟读取（Architecture V2 日视图） | READ 级别读取某个气体日已声明的 `nomination_window_masters`，同时给出声明的时钟时刻与其在该气体日解析出的 UTC 时刻。它暴露的是"声明"而非"评估"：不含市场材料、不含调度结果、不含提交动作。未配置 runtime DB 时返回空列表并在 `meta.missing_inputs` 说明原因；runtime DB 已配置但没有任何生效 master 时返回"已测量的零"并携带 `NOMINATION_WINDOWS_MISSING`，因此"今天没有窗口关闭"与"窗口未被读取"不会被混为一谈 |
| `GET /api/data-products` | Architecture V2 Wave 4（统一数据平台） | READ 级别的 Data Product 目录声明：产品 id、业务名称、可用状态、时间基准、声明的来源/授权族与今日服务端点，外加按主体的授权判定与新鲜度/溯源摘要。绝不返回 API 密钥、密钥值、调度器内部或重试轨迹；调用方无权访问的产品标记为 `restricted` 且不返回溯源块，既不省略也不显示为 0 |
| `GET/POST /api/analysis-snapshots` | Architecture V2 Wave 4（统一数据平台） | `POST`（GOVERNED，ANALYST 门槛）按当前 Active Context 记录 Analysis Snapshot 描述符；`GET` 列出最近的描述符。`GET` 保持 READ 门槛，因为描述符是血缘/溯源元数据、不含商业数值；其引用的每个数值仍在各自的商业端点之后 |
| `GET /api/analysis-snapshots/{snapshot_id}` | Architecture V2 Wave 4（统一数据平台） | 按可复现引用读取单个 Analysis Snapshot；未知引用返回 404 |

## 已声明的附加字段

对既有路径的字段级新增。它们不引入新路径、不放松门槛、不改变状态码；未发送该可选字段的调用方保持原有行为。

| 路径 | 字段 | 契约 |
|---|---|---|
| `POST /api/route-cost/recommend` | `analysis_snapshot_id`（请求可选，`data` 回显） | Architecture V2 Wave 4：产出建议所引用的可复现引用。运行前对持久化的 Analysis Snapshot 校验——未知引用返回 `422 analysis_snapshot_not_found`，无法校验时返回 `503 runtime_db_not_configured` |
| `POST /api/route-cost/resource-pool/optimize` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 5 后续把 Wave 4 的范围扩展到该运行路径：校验方式与拒绝码同建议路径一致；未引用快照时 `data` 中不出现该字段，因此此类调用方的载荷保持不变 |
| `POST /api/strategy-runs`（`run_type=BACKTEST`） | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到策略回测运行：运行前对持久化的 Analysis Snapshot 校验（被拒绝时不创建运行行、不创建作业），并在响应中回显；未引用时不出现 |
| `POST /api/analysis/query` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到分析（AI 证据）路径：在加载输入快照之前、且在调用任何 provider 之前完成校验，因此无法校验的引用绝不会以一次外部请求作为代价。拒绝码与其他路径一致；未引用时 `data` 中不出现该字段，且该引用随分析记录一并持久化 |
| `POST /api/reports/portfolio` | `analysis_snapshot_id`（请求可选，`data` 回显） | Wave 4 范围扩展到组合报告：运行前校验，在报告中回显，并作为该报告所依据的快照记入受跟踪的 `REPORT` 作业（未引用时记录为空引用）。已存储的报告记录仅保留其章节与来源引用，没有存放被引用快照的列——此处如实记录，不作暗示 |
| `GET /api/optimization/nomination-windows` | `next_gas_day`、`next_opens_at_utc`、`next_closes_at_utc`（每个窗口行，客户端可忽略） | 日视图的后续补充，且属于同一族：窗口 master 是按日生效的规则，因此当所请求气体日的窗口已关闭时，可行动的时点是同一时钟在次日的气体日发生。两个发生均由接口按气体日日历解析，而不是由客户端在时钟上加一天；忽略这三个字段的 JSON 客户端所见载荷与之前完全一致 |

## 有意收窄的行为变更

以下变更比过去**拒绝得更多**，因此记录在此（对调用方可见，且不属于纯新增）。

| 接口 | 变更 | 原因 |
|---|---|---|
| 除凭据豁免路径外的所有 `/api` 路径 | **未出示任何凭据的调用方被拒绝。** 在 D1 之前，`development` 与 `internal` 剖面根本不安装认证，会把该调用方当作兼容主体（数据范围 `("*",)`、角色 `OPERATOR`）提供服务。现在：已配置部署令牌时返回 401 `public_api_token_missing`；未配置任何令牌时 fail-closed 返回 503 `public_api_token_not_configured`；身份依赖另外保留 401 `authentication_required` 作为兜底。豁免路径为 `/api/auth/*`、`/api/dev/auth/*`、`/api/health`（含 `live`/`ready`）、`/api/dev/health` 与 `/api/internal/health` | 业主决定 D1：默认标识调用方，而"信任网络"是部署自己声明并会被上报的选择。SDK、CLI、MCP 与 Web 客户端不受影响——它们本就出示部署令牌或会话 |
| `/api/internal/*`（12 条路径） | **补上此前不存在的权限声明。** `internal` 剖面未安装路由权限闸门，因此这些路径从未解析过权限；安装闸门后暴露出：已挂载却未登记的路径会返回 500 `permission_not_declared` | 登记表是执行依据而非文档。每条登记都与该路由自身在处理器中已执行的底线一致（`validate_internal_operator_headers`），因此此前能访问者不会被新增拒绝 |

## 被拒绝的请求字段

已声明但管道从不读取的字段，是平台无法兑现的声明：填入它的调用方会收到未加修改的结果，却以为自己的选择已被应用。此类字段**以稳定错误码拒绝，而不是被忽略**，登记于此，并保持声明状态（删除它会把显式拒绝变成对仍在发送该字段的调用方的静默丢弃）。拒绝发生在运行被加载、被跟踪或被计费之前，且空值绝不构成违规。下表中每个拒绝码都已登记进产品错误分类法，因此客户端可直接分类（族、严重度、可恢复性），而不必解读原始状态码。

| 路径 | 字段 | 契约 |
|---|---|---|
| `POST /api/analysis/query` | `selected_terms`、`selected_assets`、`selected_contracts`、`include_sections` | `422 analysis_selection_not_supported`，并在 `detail.fields` 中列出每一个非空字段。确定性构建器只读取快照、任务与问题，因此术语、资产、合约或章节选择描述的是不会发生的工作。证据引用应放在 `question` 中——那正是平台记录的提示词、也是 provider 收到的文本 |
| `POST /api/reports/portfolio` | `portfolio_id`、`selected_resources`、`selected_contracts`、`selected_strategies` | 同一错误码与同一 `detail.fields` 契约：报告基于具权限的整份快照计算，因此组合/资源/合约/策略选择会成为调用方误以为已生效的范围 |
| `POST /api/agent/research` | `strategy_ir` | `422 strategy_ir_not_accepted`：编排器从不读取它，调用方可能以为自己提供的规格已被运行，而管道实际校验的是自己生成的候选。策略注册表才是拥有规格的路径 |
| `POST /api/agent/research` | `profile`（校验，非拒绝） | 不是平台已声明的 profile 时返回 `422 agent_profile_unknown`；已声明但未走完其全部阶段的 profile 以 `PROFILE_STAGES_NOT_REACHED:<stage,…>` 报告而不拒绝，因为提前停止往往是诚实的结果 |

## 弃用表

| 表面 | 弃用起始 | 计划移除 | 状态 |
|---|---|---|---|
| `/api/workflows/*`（10 个遗留壳） | 0.5.x（S4.3） | Web/SDK/CLI 全部迁移到领域化 `/api` 端点后 | 0.5.x 在 Web/SDK/CLI 迁移完成后已移除；旧路径现在返回 404 |
| `POST /api/review/decisions` 的 `actor`（请求字段） | 0.5.x（W0-03 C13） | 待无调用方再发送该字段 | 仍可接受但绝不使用：平台将已认证身份记录为决策及其审计事件的操作者。若该值与身份不一致，会以 `ACTOR_CLAIM_IGNORED:<claim>` 信封告警返回，让调用方得知其声明未被记录。同一次变更中该字段已改为可选，因此不发送才是受支持的形式 |

## 非目标

- URL 版本化（`/v1`、`/v2`）：已否决；无版本契约以只增方式演化。
- 生成式客户端桩代码：SDK DTO 保持手写，由 parity 测试守护。
