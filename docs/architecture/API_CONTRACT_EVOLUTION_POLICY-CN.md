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

1. 在 `.agent/plans/` 写 ExecPlan，列明 API 影响与回滚。
2. 新增路径：同一变更中把路径加入
   `tests/contract/test_api_surface_stability.py` 的
   `PINNED_PUBLIC_PATHS`，并更新文档化路由数（`CURRENT_PAUSE_POINT.md`、
   `-CN.md` 及 `test_architecture_alignment.py` 断言）。
3. 弃用路径：在 router 标记 `deprecated`、在信封加 warning，并登记到下方
   弃用表。
4. 先补 API、SDK、契约测试，再视为完成。
5. 运行 `AGENTS.md` 的完整验证命令集。

## 已声明的新增路径

| 路径 | 声明来源 | 契约 |
|---|---|---|
| `POST /api/optimization/portfolio-network` | R31（`V1_R31_DB_PORTFOLIO_NETWORK_EXECPLAN.md`） | 仅 DB `RUNTIME_DECISION`；只接受决策元数据，绝不接受客户端网络/费率/管容/价格事实 |
| `POST /api/optimization/storage-dispatch` | R34（`V1_R34_STORAGE_NOMINATION_CLIENT_WORKFLOWS_EXECPLAN.md`） | 仅评估的储气调度；RUNTIME_DECISION 组装 PostgreSQL master/观测 |
| `POST /api/optimization/nomination-window` | R34 | 仅评估的提名窗口；RUNTIME_DECISION 读取 DB 窗口 master；无提交动作 |

## 弃用表

| 表面 | 弃用起始 | 计划移除 | 状态 |
|---|---|---|---|
| `/api/workflows/*`（10 个遗留壳） | 0.5.x（S4.3） | Web/SDK/CLI 全部迁移到领域化 `/api` 端点后 | 0.5.x 在 Web/SDK/CLI 迁移完成后已移除；旧路径现在返回 404 |

## 非目标

- URL 版本化（`/v1`、`/v2`）：已否决；无版本契约以只增方式演化。
- 生成式客户端桩代码：SDK DTO 保持手写，由 parity 测试守护。
