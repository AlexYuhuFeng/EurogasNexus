# S4.4: Actor 身份模型（最小形态）ExecPlan

## 1. Goal

为 S2 信任链的 actor 提供最小但统一的身份模型：唯一 principal 校验器 +
双语身份模型文档，让复核、审计、internal 写入、认证证据四处的 actor 规则一致。
多用户认证/SSO 明确留在 R32（非本计划）。

## 2. Non-goals

- 不做账户/会话/RBAC/SSO/OIDC。
- 不新增表（actor 沿用既有 `review_decisions.actor`、`audit_events.principal`）。
- 假数据 pipeline 零 diff；无新依赖。

## 3. Product boundary

- 校验规则唯一实现在 `domain/identity/principal.normalize_principal`。
- 执行点：`db/repositories/review.py`（actor）、
  `security/internal_api.py`（X-Eurogas-Principal 头，空值保留
  `internal_principal_missing` 错误码）、`domain/ingestion/certification.py`
  （evaluated_by）。

## 4. Files to create/modify

- create `src/eurogas_nexus/domain/identity/__init__.py`
- create `src/eurogas_nexus/domain/identity/principal.py`
- modify `src/eurogas_nexus/db/repositories/review.py`
- modify `src/eurogas_nexus/security/internal_api.py`
- modify `src/eurogas_nexus/domain/ingestion/certification.py`
- create `tests/unit/test_principal.py`
- create `docs/architecture/ACTOR_IDENTITY_MODEL.md` + `-CN.md`
- modify `docs/architecture/IMPROVEMENT_ROADMAP.md`、`RELEASE_READINESS.md`/`-CN.md`

## 5. Dependency policy

零新依赖。

## 6. Data policy

无数据变更；既有行不动。

## 7. API impact

无路径变化；internal principal 头的非法字符校验收紧（新错误码
`internal_principal_invalid`，空值仍是 `internal_principal_missing`）。

## 8. DB impact

无。

## 9. Tests

- `tests/unit/test_principal.py`：合法/非法矩阵。
- 既有 review/internal/certification 测试全绿（覆盖错误码兼容）。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
ruff check src tests scripts
pytest tests/unit/test_principal.py tests/unit/test_review_repository.py tests/api/test_internal_market_positioning_import.py tests/api/test_source_certification_api.py tests/unit/test_certification_gate.py -q -p no:cacheprovider
pytest tests/api tests/contract tests/unit tests/sdk -q -p no:cacheprovider
```

## 11. Acceptance criteria

- 四处 actor 入口共用同一校验器；非法 principal 拒绝写入。
- 全量回归 0 失败（沙箱既有 DB-backed error 除外）；路由数 90；head 0018。

## 12. Rollback notes

- 纯代码 + 文档；回退提交即可。行为差异仅在「非法字符 principal 从可写变拒绝」。
