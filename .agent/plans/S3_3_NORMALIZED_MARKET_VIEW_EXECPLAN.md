# S3.3: 规范化市场视图 API ExecPlan（后端部分）

## 1. Goal

把前端 `clients/web/src/app/marketPriceNormalization.ts` 重实现的领域逻辑
（FX 汇率图转换、hub/tenor 抽取、气体价格判定）下沉为后端拥有的
「规范化市场视图」API，让客户端消费后端计算好的行（含 `price_gbp_mwh`），
消除双实现漂移（路线图问题 P2 / S3.3）。

> 本 ExecPlan 只交付后端 + SDK。前端删除 `marketPriceNormalization` 重实现
> 按用户指示「先把后端都搞完」推迟到前端阶段（S3.3 前端子任务）。

## 2. Non-goals

- 不改假数据 pipeline（零 diff）。
- 前端改造（删除/替换 TS 实现、组件切换数据源）不在本计划。
- 不新增「策略场景组装」后端化（SAP/ICIS/OCM 挑选仍是前端场景逻辑）。
- 无 Kafka/Redis、无新依赖、无 DDL。

## 3. Product boundary

- 新端点 `GET /api/market/normalized`：读 PostgreSQL，返回规范化行
  （原始观测字段 + `hub` / `tenor` / `is_gas_price` / `price_gbp_mwh`）。
- 语义与现有前端实现逐条对齐（汇率图 BFS ≤ 3 跳、最新汇率按 observed_at 取、
  hub 取 metadata_json.hub → product 首词 → venue、tenor 取 metadata_json.tenor
  → product、气体价 = unit 含 MWH 且货币为 3 位代码）。
- FX 行缺失时回退到 ECB `market_observations`（与 `/api/market/fx` 现有行为一致）。
- 信封沿用 `/api/market/*` 的 `data/meta` 约定；不可转换的行返回
  `price_gbp_mwh: null` 并在 meta.warnings 中列出 observation_id。

## 4. Files to create/modify

- create `src/eurogas_nexus/domain/market_intelligence/normalized_view.py`
  （纯函数域模块：`FxRateInput` / `MarketObservationInput` / `convert_currency` /
  `observation_hub` / `observation_tenor` / `is_gas_price` /
  `build_normalized_market_view`）
- modify `src/eurogas_nexus/db/repositories/market_intelligence.py`
  （`list_normalized_market_view(session, *, limit)`：DB 组装 → 域模块计算）
- modify `src/eurogas_nexus/api/routes/public/market.py`
  （`GET /api/market/normalized`，DB 不可用降级信封）
- modify `src/eurogas_nexus/sdk/market.py`
  （`NormalizedMarketObservation` DTO + `fetch_normalized_market_observations*`）
- create `tests/unit/test_normalized_market_view.py`
- create `tests/api/test_market_normalized_api.py`
- modify `tests/sdk/test_intraday_market_clients.py`（新 SDK 方法覆盖）
- modify `tests/contract/test_architecture_alignment.py`（路由数 89→90）
- modify `docs/architecture/CURRENT_PAUSE_POINT.md` + `-CN.md`（路由数 90 + 产品形态）
- modify `docs/architecture/IMPROVEMENT_ROADMAP.md`（S3.3 后端部分 ✅，前端部分标注 defer）
- create `.agent/plans/S3_3_NORMALIZED_MARKET_VIEW_EXECPLAN.md`（本文件）

## 5. Dependency policy

零新依赖。仅用标准库 + 既有 SQLAlchemy/Pydantic。

## 6. Data policy

- 只读：不改任何表；规范化结果不落库（派生视图，源头仍是原始观测行）。
- 汇率语义：EUR 基准参考汇率（ECB），图转换最多 3 跳，超过不给数（与前端一致）。
- 不可转换/非法汇率不静默出价：`price_gbp_mwh = null` + meta.warnings 点名行。

## 7. API impact

- 新增 `GET /api/market/normalized`（公开只读，research_only 信封）。
- 公开路径数 89 → 90。
- 既有端点零改动。

## 8. DB impact

无 DDL、无迁移。`alembic heads` 保持 `0017_review_decisions`，37 表不变。

## 9. Tests

- 域模块单元测试：转换（同币/直连/反向/跨币/超 3 跳/非法汇率/最新汇率选取）、
  hub/tenor 抽取优先级、is_gas_price 判定、视图构建与 warnings。
- API 测试：DB 未配置 → 空数据 + 明确 warning；信封字段。
- SDK 测试：新方法 URL 与 DTO 解析。
- 契约测试：路由数 90 更新。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
ruff check src tests scripts
pytest tests/unit/test_normalized_market_view.py tests/api/test_market_normalized_api.py tests/sdk/test_intraday_market_clients.py -q -p no:cacheprovider
pytest tests/api tests/contract tests/unit tests/sdk -q -p no:cacheprovider
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"   # 90
python -m alembic heads                                                          # 0017_review_decisions
git status --porcelain -- src/eurogas_nexus/ingestion scripts/ops/ingest_simulated_market_prices.py scripts/ops/seed_preview_runtime_data.py   # 空
```

## 11. Acceptance criteria

- `/api/market/normalized` 返回的行含后端计算的 `hub`/`tenor`/`is_gas_price`/
  `price_gbp_mwh`，语义与现有前端函数逐条一致（测试钉死）。
- DB 不可用时返回显式降级信封（不静默）。
- SDK 提供 `fetch_normalized_market_observations`。
- 路由数 90；alembic head 不变；ruff 干净；假数据 pipeline 零 diff；
  前端文件零改动（后端优先边界）。

## 12. Rollback notes

- 纯增量：删除新端点 + 回退 SDK/测试即可；无迁移、无数据变更。
- 前端阶段接入时若语义需要微调，域模块是唯一改动点（后端契约集中化收益）。
