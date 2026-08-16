# Phase 1: 近实时决策管线 ExecPlan

## 1. Goal

把消费模型从「10 秒轮询 + 定时全扫」升级为「SSE 推送 + 增量消费」，并把分析粒度参数化、补上管线可观测性基线。端到端目标（仿真源）：quote 落库 → 客户端可见 **< 2 秒**，机会/告警产出 **< 3 秒**。

## 2. Non-goals

- 不修改假数据 pipeline（`ingestion/simulated_market_prices.py` 及其 `--loop`、seed 脚本零改动，D8）。
- 不引入 Kafka/Redis/任何新依赖（SSE = FastAPI `StreamingResponse`，客户端 = 原生 `EventSource`）。
- 不做 WebSocket、不做亚秒策略、不改 PostgreSQL 唯一真相（SSE 只是只读交付通道）。
- 不做复核/审计/保留策略（阶段 2/3）。

## 3. Product boundary

决策支持 + human-review 不变。SSE 推送的是**已落 PG 的事实**（quotes/opportunities/alerts），客户端不能通过推送通道绕过 API 语义；轮询保留为 fallback。

## 4. Files to create/modify

- Create `src/eurogas_nexus/api/routes/public/streaming.py`
  - `GET /api/stream/quotes`、`/api/stream/opportunities`、`/api/stream/alerts`
  - 每个 = `StreamingResponse` 生成器：每 ~1.5s 读 PG、按水位线（max `observed_at_utc`/`quote_id`）只推增量；~15s 心跳注释；DB 不可用则推 warning 事件并重试。
- Create `src/eurogas_nexus/application/pipeline_health.py`
  - `pipeline_health(session) -> dict`：按源聚合 `ingestion_runs`（最近状态/连续失败）、`market_quotes`（每源最新 `observed_at_utc` + 近 N 分钟条数）、`intraday_opportunities`（最近 `detected_at_utc`）、`monitoring_alerts`（open 数）。
- Modify `src/eurogas_nexus/api/routes/public/runtime.py` — 加 `GET /api/runtime/pipeline-health`（DB 不可用降级为空+警告）。
- Modify `src/eurogas_nexus/api/route_registration.py` — 注册 streaming router。
- Modify `scripts/ops/run_monitoring_worker.py` — interval 下限 5s → 2s（默认保持 10s，加 `--interval-seconds 2` 说明）。
- Modify `clients/web/src/api/client.ts` — SSE 订阅 helper（`EventSource` + 回退）。
- Modify `clients/web/src/stores/api.ts` — 订阅 quotes/opportunities/alerts 事件并更新 store；保留 10s 轮询 fallback。
- Modify `clients/web/src/app/strategyScenario.ts` + `StrategyShadowRunTerminal.tsx` — `bar_minutes` 可配置（1/5/15，默认 5 兼容）。
- Modify `clients/web/src/i18n/en.json`、`zh.json` — 新标签（streaming 状态、pipeline-health、bar 选择）。
- Tests: Create `tests/api/test_streaming_api.py`、`tests/unit/test_pipeline_health.py`；Modify `tests/contract/test_client_release_surface.py`（SSE 契约断言）。

## 5. Dependency policy

零新增。仅 FastAPI/Starlette 原生 `StreamingResponse`、浏览器原生 `EventSource`、标准库。

## 6. Data policy

PostgreSQL 仍是唯一真相。SSE 端点**只读** PG、只推增量；不在内存里缓存真相；水位线只是游标。客户端状态仍以 API 数据为权威，推送只是加速。

## 7. API impact

- 新增 `GET /api/stream/quotes`、`/api/stream/opportunities`、`/api/stream/alerts`（`text/event-stream`）。
- 新增 `GET /api/runtime/pipeline-health`。
- 既有端点不变。

## 8. DB impact

无 schema 变更、无迁移。全部只读。

## 9. Tests

- API：SSE 端点返回 200 + `text/event-stream`；首帧含 `retry:`；DB 不可用时推 warning 事件而非报错。
- Unit：`pipeline_health` 聚合正确（按源新鲜度/失败计数/open 告警）。
- Contract：SSE 路由在 route registration；web 含 `EventSource` 且有轮询 fallback。
- 回归：既有 474 测试全绿。

## 10. Validation commands

```powershell
ruff check src tests
pytest -q tests/api/test_streaming_api.py tests/unit/test_pipeline_health.py tests/contract -p no:cacheprovider
python -c "from apps.api.main import app; print('app import ok'); print(len(app.openapi()['paths']))"
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json   # (clients/web)
```

## 11. Acceptance criteria

- SSE 三个端点可用，推送增量 < 2 秒（仿真源，D1）。
- 监控 worker 可在 2–3 秒节奏运行（D1）。
- `bar_minutes` 1/5/15 可配置，默认 5 兼容（D5）。
- `pipeline-health` 展示每源新鲜度/失败/告警（D2）。
- 假数据 pipeline 零改动（`git diff` 该目录为空，D8）。

## 12. Rollback notes

- SSE 是纯增量端点：删除 `streaming.py` + 取消注册即回滚，无数据迁移。
- Web 保留轮询 fallback：回滚 = 恢复纯轮询。
- worker interval 是脚本参数，改回默认即回滚。
