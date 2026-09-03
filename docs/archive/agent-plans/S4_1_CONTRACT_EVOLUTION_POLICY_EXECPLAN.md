# S4.1: 契约演化策略 ExecPlan

## 1. Goal

为 stable unversioned `/api` 建立成文的契约演化策略（版本化/弃用政策）并配套
一个可执行的兼容测试门，让 5 个消费表面（Web/SDK/CLI/Desktop/文档）的漂移
在 CI 里失败而不是靠自觉。落地路线图 S4.1。

## 2. Non-goals

- 不引入 `/v1`/`/api/v1` 别名、不做 API 版本号 URL。
- 不迁移/改写现有路由。
- 不做 OpenAPI 代码生成或 schema 快照文件（仅钉路径集合）。
- 假数据 pipeline 零 diff；无新依赖、无 DDL。

## 3. Product boundary

- 政策适用面：公开 `/api`、`/api/internal`、`/api/dev`、SDK DTO、文档计数。
- 兼容门只钉「路径集合 + 前缀规则」；字段级兼容由既有
  `test_sdk_backend_parity.py`（SDK↔后端）继续负责。

## 4. Files to create/modify

- create `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md` + `-CN.md`
  （原则：只增不改、弃用流程、破坏性变更禁令、5 surface 同步、审计要求）
- create `tests/contract/test_api_surface_stability.py`
  （钉死 90 条公开路径集合；禁止 `/v1` 前缀；任何增删必须在测试里显式声明）
- modify `docs/architecture/IMPROVEMENT_ROADMAP.md`（S4.1 ✅）
- modify `docs/release/RELEASE_READINESS.md` + `-CN.md`（产品形态增补）

## 5. Dependency policy

零新依赖。

## 6. Data policy

无数据变更。

## 7. API impact

无路由变化；路径数保持 90。

## 8. DB impact

无。

## 9. Tests

- `test_api_surface_stability.py`：
  - live `app.openapi()['paths']` 集合 == 钉死集合（90 条）；
  - 无路径以 `/v1`/`/api/v1` 开头；
  - 每条路径都以 `/api/`、`/api/internal/` 或 `/api/dev/` 开头。
- 既有契约/parity 测试保持全绿。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
ruff check src tests scripts
pytest tests/contract/test_api_surface_stability.py -q -p no:cacheprovider
pytest tests/api tests/contract tests/unit tests/sdk -q -p no:cacheprovider
python -c "from apps.api.main import app; print(len(app.openapi()['paths']))"   # 90
```

## 11. Acceptance criteria

- 政策文档双语存在并链接到兼容门。
- 路径集合兼容门在 CI 可执行；新增/删除公开路由不更新测试即红。
- 全量回归 0 失败（沙箱既有 26 个 DB-backed error 除外）。

## 12. Rollback notes

- 纯文档 + 测试增量；回退即删除两文件并还原文档标记。
