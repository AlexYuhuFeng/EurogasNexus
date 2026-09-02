# S3.2: 公共源摄入幂等化 ExecPlan

## 1. Goal

让 `public_sources` 摄入路径（`scripts/ops/ingest_public_sources.py`）在重跑时收敛到
相同的持久化状态：自然键 upsert、无重复、部分/空载荷不会破坏已有数据。落地路线图
[IMPROVEMENT_ROADMAP-CN.md](../../docs/architecture/IMPROVEMENT_ROADMAP-CN.md) 的 S3.2 与
问题 E，并顺带补齐 S2.2 中「摄入重跑写 audit_events」的覆盖。

## 2. Non-goals

- 不改假数据 pipeline（`ingestion/simulated_market_prices.py`、
  `scripts/ops/ingest_simulated_market_prices.py`、`seed_preview_runtime_data.py`）——零 diff。
- 不改任何表结构/迁移、不加路由、不加依赖。
- 不引入 Kafka/Redis。
- 不实现分区或归档（S3.1 已交付保留清理，本步只保证「重跑安全」）。

## 3. Product boundary

- PostgreSQL 仍是唯一真相；摄入脚本为 operator 显式调用（或 60s+ 定期 worker 调用）。
- 审计为追加式只写；principal 沿用既有脚本约定 `operator`（身份模型 M4.4 另立）。
- 重跑语义按记录类型划分：观测记录 = 自然键 upsert（first-seen `observed_at_utc`）；
  参考网络 = 按 source_system 作用域的全量快照替换（空载荷跳过、绝不清空）。

## 4. Files to create/modify

- create `src/eurogas_nexus/db/repositories/public_ingestion_upsert.py`
  - `upsert_observation_rows(session, model, rows)`：PG `INSERT ... ON CONFLICT
    (natural PK) DO UPDATE`，SET 排除 `observed_at_utc`（first-seen）。
  - `replace_reference_snapshot(session, model, rows, *, source_system)`：
    非空才替换；删除仅限该 source_system；SET 排除 `created_at_utc`。
- modify `scripts/ops/ingest_public_sources.py`
  - ECB/FX、ENTSOG flow/capacity、GIE AGSI/ALSI：`session.merge` → `upsert_observation_rows`。
  - 删除 flow 路径的 `delete(FlowObservationRecord).where(source_system=="ENTSOG")`
    （全量替换在 `--limit` 窗口下会造成既有数据丢失；保留策略已接管生命周期）。
  - `_replace_reference_network` 重写：逐表非空守卫 + source 作用域删除；派生表
    （`reference_edges`/`node_facility_mappings`/`topology_market_mappings`，operator 维护）
    不再被摄入路径触碰；全空时抛错并保留既有拓扑；空表跳过并在报告 warnings 说明。
  - `_record_run` 增加 `record_audit_event`（event_type=ingestion，含失败路径）。
- create `tests/unit/test_public_ingestion_upsert.py`
- create `tests/unit/test_ingest_public_sources.py`
- modify `docs/architecture/IMPROVEMENT_ROADMAP.md`（S3.2 标记 ✅）
- modify `docs/architecture/CURRENT_PAUSE_POINT.md` + `-CN.md`（产品形态增补一行）

## 5. Dependency policy

零新依赖。仅使用 SQLAlchemy 2.0 Core（`sqlalchemy.dialects.postgresql.insert`）——
运行时唯一方言是 PostgreSQL（`src/` 下无 sqlite 用法，已核实）。

## 6. Data policy

- 观测记录自然键即 `observation_id`（ECB/GIE 按日期+货币/设施确定；ENTSOG 按 provider
  record id 确定），已核实确定性——重跑同载荷生成同 id。
- `observed_at_utc`/`created_at_utc` 采用 first-seen 语义，重跑不漂移；管道活动时间
  由 `ingestion_runs`（每次运行新行）承载，两者职责分离。
- 参考网络替换删除按 `source_system == "ENTSOG"` 作用域执行；若 operator 边/映射引用
  被移除的节点，FK 会让整笔事务回滚（fail-loud，绝不静默清数据）。
- 空/部分载荷视为 provider 故障而非「网络变空」：跳过或整体报错。

## 7. API impact

无。公开 API 路径数（84）、schema、SDK DTO 均不变。

## 8. DB impact

无 DDL。`alembic heads` 保持 `0017_review_decisions`；表数保持 37。

## 9. Tests

- 仓储模块：upsert 语句编译（PG 方言）含 `ON CONFLICT (observation_id) DO UPDATE`、
  SET 不含 `observed_at_utc`；空行不触库；快照替换空载荷不删除；删除限定 source；
  无 `source_system` 列的表报 `ValueError`。
- 脚本：`_replace_reference_network` 全空抛错、部分空跳表并报告；`_record_run` 写审计。
- 既有 `tests/ingestion/test_public_source_ingestion.py` 归一化测试保持全绿。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
ruff check src tests scripts
pytest tests/unit/test_public_ingestion_upsert.py tests/unit/test_ingest_public_sources.py tests/ingestion -q -p no:cacheprovider
pytest tests/api tests/contract tests/unit -q -p no:cacheprovider
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"   # 84
python -m alembic heads                                                          # 0017_review_decisions
git status --porcelain -- src/eurogas_nexus/ingestion scripts/ops/ingest_simulated_market_prices.py scripts/ops/seed_preview_runtime_data.py   # 空（假数据 pipeline 零 diff）
```

## 11. Acceptance criteria

- 同一载荷重跑两次：观测表行数不增、数值收敛；`observed_at_utc` 不因重跑改写。
- 空/部分参考载荷不再清空既有参考网络；operator 维护的边/映射不被摄入路径删除。
- 每次摄入（成功与失败）写入 `audit_events` 与 `ingestion_runs`。
- 全部上述测试绿；ruff 干净；路由数 84；alembic head `0017_review_decisions`；假数据
  pipeline 零 diff。

## 12. Rollback notes

- `git revert` 本计划提交即可整体回退；无迁移、无路由、无依赖。
- 行为差异点：ENTSOG flow 不再「删旧插新」，历史窗口行会累积并由 S3.1 保留策略清理；
  如现场反馈需要窗口式替换，可加显式 `--replace-window` 开关，但默认保持 upsert。
