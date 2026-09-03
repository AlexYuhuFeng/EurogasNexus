# S4.2: Provider 认证门 ExecPlan

## 1. Goal

让「真实（licensed）适配器」只有通过「模拟→真实」认证门之后才能被标记为
native live；未过门（包括 DB 不可用）一律 fail-closed。落地路线图 S4.2 与
问题 P4（真实 connector 是 research_only 壳，未验证不能冒充 live）。

## 2. Non-goals

- 不实现任何真实 provider 网络调用或 connector 本体。
- 不改假数据 pipeline（零 diff）。
- 不给任何现有 licensed 源「自动发证」：初始状态全部 `unverified`（诚实）。
- 无新依赖。

## 3. Product boundary

- 认证证据持久化到 PostgreSQL（`provider_certifications`），运行时门以 DB 为准；
  DB 不可用 → `unverified` → 不允许 native live（fail-closed）。
- 认证由 internal operator 端点写入（token + principal + 审计事件）。
- 公开 `/api/sources` 只读展示 `certification_stage` 与
  `certification_allows_live`；`operational_status` 的 native `active`
  从此必须过门。

## 4. Files to create/modify

- create `alembic/versions/0018_provider_certifications.py`
- create `src/eurogas_nexus/db/models/certification.py`
  （`ProviderCertificationRecord`，表 `provider_certifications`）
- modify `src/eurogas_nexus/db/models/__init__.py`（导出）
- modify `src/eurogas_nexus/db/registry.py`（38 张必需表）
- create `src/eurogas_nexus/domain/ingestion/__init__.py`
- create `src/eurogas_nexus/domain/ingestion/certification.py`
  （`CertificationStage`、`REQUIRED_LIVE_CHECKS`、`certification_gate()`、
  `validate_certification_payload()`）
- create `src/eurogas_nexus/db/repositories/certification.py`
  （upsert + latest + list；写审计）
- create `src/eurogas_nexus/api/routes/internal/source_certification.py`
  （`POST /api/internal/sources/certification`）
- modify `src/eurogas_nexus/api/routes/internal/router.py`（注册）
- modify `src/eurogas_nexus/api/routes/public/sources.py`
  （认证字段 + `_attach_operational_status` 过门判定）
- create `tests/unit/test_certification_gate.py`
- create `tests/unit/test_certification_repository.py`
- create `tests/contract/test_certification_db_models.py`
- create `tests/api/test_source_certification_api.py`
- modify `tests/contract/test_architecture_alignment.py`（0018 / 38）
- modify `docs/release/RELEASE_READINESS.md` + `-CN.md`（head 0018、38 表、产品形态）
- modify `docs/architecture/IMPROVEMENT_ROADMAP.md`（S4.2 ✅）

## 5. Dependency policy

零新依赖。

## 6. Data policy

- 认证记录为 operator 显式写入的证据（append + upsert by source_system），
  非自动推断；初始为空 = 全 `unverified`。
- 门只读 DB；`live_validated` 必须包含 `simulated_shape_match` 与
  `live_sample_validation` 两项检查证据，否则拒绝。

## 7. API impact

- 新增 internal 端点（internal 路由不在公开 openapi 集合内，公开路径数保持 90）。
- `/api/sources` 每源新增两个只读字段。

## 8. DB impact

- 迁移 `0018_provider_certifications`（1 新表）；必需表 37→38；
  `alembic heads` = `0018_provider_certifications`。

## 9. Tests

- 域门：stage/检查组合矩阵（unverified/simulation_matched 拒绝 live；
  live_validated 缺检查拒绝；齐备放行；非法载荷 ValueError）。
- 仓储：MagicMock（upsert+审计、latest、list）。
- 契约：模型字段 + registry 含新表。
- API：无 token → 401；DB 未配置 → 503；认证写入 happy path（SQLite）；
  `/api/sources` 未认证源即使有 live records 也不得 native active
  （DB-free posture 单测）。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
ruff check src tests scripts
pytest tests/unit/test_certification_gate.py tests/unit/test_certification_repository.py tests/contract/test_certification_db_models.py tests/api/test_source_certification_api.py -q -p no:cacheprovider
pytest tests/api tests/contract tests/unit tests/sdk -q -p no:cacheprovider
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"   # 90
python -m alembic heads                                                          # 0018_provider_certifications
```

## 11. Acceptance criteria

- 未过门 licensed 源永远不能 `operational_status="active"`（含 DB 不可用）。
- 过门证据可经 internal 端点写入并审计；公开源列表可见认证阶段。
- 全量回归 0 失败（沙箱既有 DB-backed error 除外）；路由数 90；head 0018。

## 12. Rollback notes

- 删除迁移前先 downgrade（`alembic downgrade 0017`）；回退代码即回退门。
- 门是 fail-closed：回退后 licensed 源恢复「凭记录数标 active」的旧行为，
  属预期（旧语义）。
