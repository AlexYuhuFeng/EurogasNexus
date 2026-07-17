# 优化层

英文主文档：[PHASE_TWO_OPTIMIZATION.md](PHASE_TWO_OPTIMIZATION.md)

## 目的

优化包为欧洲天然气业务提供确定性的、必须由交易员复核的决策支持。它不会提交订单、提名、管容预订、合同修改或审批。所有结果都保留
`human_review_required=True`。

代码目录：

```text
src/eurogas_nexus/optimization/
```

## 能力状态

| 能力 | 模块 | 状态 | 对外边界 |
|---|---|---|---|
| 满足管容约束的单路径选择 | `route.py` | 稳定的确定性模型 | 统一服务 + API |
| 资源池分配 | `resource_pool.py` | 适用于已说明可分模型的稳定启发式算法 | 统一服务 + API |
| 管容产品选择 | `capacity.py` | 面向有限产品集合的精确子集模型 | 统一服务 + API |
| 单日合同调度 | `contract.py` | 面向单一市场净回值的稳定确定性模型 | 统一服务 + API |
| 共享管容网络流 | `network_flow.py` | 已验证的残量网络模型 | 仅 Python 内部模块 |
| 多周期储气调度 | `storage.py` | 已验证的网格化原型 | 仅 Python 内部模块 |
| 提名窗口评估 | `nomination.py` | 已验证的规则原型 | 仅 Python 内部模块 |

`PhaseTwoOptimizer` 目前只对前四项能力提供稳定门面。后三个模块暂不导出到统一服务或公共 API；在对外开放前，必须先完成基于 PostgreSQL 的输入组装、DTO、数据来源追踪和产品工作流评审。

## 公共 API

```text
POST /api/optimization/route
POST /api/optimization/resource-pool
POST /api/optimization/capacity
POST /api/optimization/contracts
```

这些端点接收明确的操作员输入，并统一返回 `data/meta` 信封。`meta.source_references` 为 `operator-input`，所有结果都要求人工复核。`meta.research_only` 仅作为现有公共信封的临时兼容字段保留，不得进入新的业务数据 DTO。

## 模型边界

### 单路径模型

在过滤停用边、管容不足边和公司无权使用的 TSO 后，选择总费率最低的有向路径。该模型只处理一个数量和一条路径，不处理多个资源共享管线容量的问题。

### 资源池模型

先安排合同最低提取量，再分配正边际的可选数量，并约束资源上限、销售选项上限和 TSO 权限。当前贪心实现具有确定性，但对于任意的资源与市场配对权限图，不宣称全局最优。共享物理管容应交由网络流模型处理。

### 管容产品模型

穷举输入产品的子集，选择能够覆盖所需管容且成本最低的组合。对于输入的有限产品集合，该结果是精确的；它不适用于未经筛选的大规模拍卖产品全集。

### 合同调度模型

先处理最低提取量，再按单一市场净回值使用正边际弹性。当前不处理跨期 Take-or-Pay 累计、补提气、价格选择权、多销售目的地或跨期合同限制。

### 共享管容网络流

该模型是确定性的、线性的、有向的单一天然气商品最小成本流模型，包含：

- 多供应点和多需求点的超级源点、超级汇点；
- 采购成本、物理管线费率和销售点价值；
- 正向与反向残量弧；
- 当早期分配阻塞更优组合时撤销并重新路由；
- 多资源共享物理管容和 TSO 权限过滤；
- 对最终流量执行流守恒、管容、成本和目标值校验。

严格负边际的可选流量不会被输送，零边际流量按确定性顺序处理。该模型不是水力学仿真，不处理压力、管存、压缩机耗气、气质或提名执行。

### 储气调度原型

使用库存网格和动态规划处理多个价格周期。初始库存和指定的期末库存不会被静默取整，并对库存、注采速率、效率和成本做显式校验。结果依赖网格精度，不代表连续模型的精确最优解。

### 提名窗口原型

根据调用方提供的时间窗口和变更限制评估提名指令。它只提供规则评估，不会提交提名。调用方必须先把时间戳转换到相关运营商采用的时间基准。

## 数据和数据库边界

- 优化包在导入时不连接数据库或网络。
- 当前四个公共优化端点使用请求中明确提供的数据，并标记为 `operator-input`。
- 正式工作流必须从 PostgreSQL 组装合同、费率、管容、TSO 权限和市场观测后再调用模型。
- 数据库缺失的信息必须成为阻断项，模型不得自行编造。

## 验证

```bash
ruff check src/eurogas_nexus/optimization tests/optimization
pytest -q tests/optimization tests/api/test_optimization_routes.py
```

仓库标准验收命令：

```bash
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 下一次对外扩展前的必备工作

1. 定义基于 PostgreSQL 的输入组装和数据来源追踪合同；
2. 定义兼容性安全的 API DTO 和 SDK 方法；
3. 增加中英文客户端工作流规范；
4. 按需要增加跨期合同与路径耦合；
5. 单独评审可选、许可证宽松的求解器适配层；
6. 继续保持人工复核和禁止执行交易的边界。
