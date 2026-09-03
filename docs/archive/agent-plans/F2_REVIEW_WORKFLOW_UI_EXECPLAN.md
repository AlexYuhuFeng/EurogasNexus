# F2: 复核工作流 UI（持久化决策）ExecPlan

## 1. Goal

把 Review 工作区从「只读展示 + LLM 分析」升级为真实的后端复核工作流：
读写 `review_decisions`（`GET/POST /api/review/decisions`，后端已交付），
让「candidate → reviewed → accepted/rejected/needs_attention」在界面上可执行、
可追溯（谁、何时、什么决定，全部落库 + 审计）。

## 2. Non-goals

- 不做任何本地持久化：**actor 只存在于页面内存**（React state，默认
  `operator`），刷新即回到默认——真实身份等 R32（用户已确认此方案）。
- 不改后端（两个 review 端点已交付并测试）。
- 不把决策状态嵌入 Strategy 终端/机会列表（留作可选 F2b）。
- 零新依赖；假数据 pipeline 零 diff；不碰 `GasNetworkMap`。

## 3. Product boundary

- Review 工作区新增两块：**决策历史流**（GET 列表，可按实体过滤）与
  **决策记录器**（entity_type / entity_id / 三个决策按钮 / note / actor）。
- actor 校验依赖后端 `normalize_principal`（非法 principal 后端 4xx，前端只做
  非空提示）。
- 无真实身份之前，决策按钮旁边明示「operator 身份为页面内输入，未经 SSO 认证」
  （诚实提示文案，双语）。

## 4. Files to create/modify

- modify `clients/web/src/api/client.ts`
  - `ReviewDecisionDTO`（decision_id/entity_type/entity_id/actor/decision/
    note/created_at_utc）、`ReviewDecisionInputDTO`
  - `api.reviewDecisions(params?)`、`api.recordReviewDecision(body)`
- modify `clients/web/src/stores/api.ts`
  - `reviewDecisions: ReviewDecisionDTO[]`；`fetchWorkspace` 拉
    `api.reviewDecisions()`；新增 `recordReviewDecision(body)`（POST 后重拉列表）
- modify `clients/web/src/components/ReviewWorkspace.tsx`
  - props 增 `reviewDecisions`、`reviewMessage`、`onRecordDecision`
  - 新面板：决策历史（表格）+ 决策记录器（select/input/三按钮/note/actor，
    actor 用 `useState("operator")`，无 localStorage）
  - 预填：entity_type 默认 `strategy_run`，entity_id 有最新 strategy run 时预填
    `run_id`，否则留空输入
- modify `clients/web/src/app/workspaces/WorkspaceRenderer.tsx`（传 props）
- modify `clients/web/src/i18n/en.json` + `zh.json`（新 key，双语）
- modify `clients/web/src/styles/app.css`（review 决策区样式，沿用现有
  `data-table`/`action-row` 类族，尽量不加新类）
- modify `tests/contract/test_trader_client_correctness.py`（新增断言：Review
  工作区消费 review API；actor 为页面内存 useState；无 `localStorage` 业务写入；
  双语 key 存在）

## 5. Dependency policy

零新依赖。

## 6. Data policy

- 决策数据只经 API 落 PostgreSQL（`review_decisions` + `audit_events`）。
- 前端不持久化任何业务数据；actor 仅在组件内存。

## 7. API impact

无后端变更（复用 `GET/POST /api/review/decisions`）。

## 8. DB impact

无（表已在 0017 迁移交付）。

## 9. Tests

- 契约测试新增：
  - `api.reviewDecisions` / `api.recordReviewDecision` 出现在 client.ts；
  - `ReviewWorkspace` 消费 `reviewDecisions` 并调用 `onRecordDecision`；
  - actor 由 `useState("operator")` 承载且客户端无 localStorage 业务写入；
  - 新 i18n key 在 en/zh 均存在（既有双语测试自动覆盖组件内字面 key）。
- 既有契约/后端测试保持全绿；`tsc --noEmit` + vite build 通过。

## 10. Validation commands

```powershell
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
python -m pytest tests/contract -q -p no:cacheprovider
# clients/web 下:
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json
node node_modules/vite/bin/vite.js build
git status --porcelain -- src/eurogas_nexus/ingestion scripts/ops/ingest_simulated_market_prices.py scripts/ops/seed_preview_runtime_data.py
```

## 11. Acceptance criteria

- Review 工作区可列出决策历史、可提交 accepted/rejected/needs_attention +
  note，成功后列表刷新且显示落库的 actor/时间。
- actor 默认 `operator`、可改、仅页面内存（刷新复位）。
- DB 不可用时接口返回显式 warning（复用后端行为，前端展示即可）。
- 契约测试 + tsc + build 全绿；假数据 pipeline 零 diff。

## 12. Rollback notes

- 纯前端增量：`git revert` 即回退；后端端点保留无影响。
