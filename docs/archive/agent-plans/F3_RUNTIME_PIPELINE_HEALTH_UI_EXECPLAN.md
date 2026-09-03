# F3: Runtime 管线健康 + 流式状态指示 ExecPlan

## 1. Goal

把阶段 1 的可观测性能力真正展示到客户端：
- Runtime 工作区新增「管线健康」面板（消费 `GET /api/runtime/pipeline-health`）：
  每源状态/连续失败/最近成功、报价新鲜度（近 5 分钟计数 + 最新观测时间）、
  开放告警数、最新机会时间；
- 顶栏新增数据模式徽章：SSE 实时推送 vs 10s 轮询兜底（`streamingActive` 驱动），
  让「近实时是否生效」一眼可见。

## 2. Non-goals

- 不改后端（端点已交付：`/api/runtime/pipeline-health`）。
- 不做告警详情/图表/趋势；只展示后端聚合的事实。
- 零新依赖；假数据 pipeline 零 diff；不碰 `GasNetworkMap`。

## 3. Product boundary

- 客户端只读展示后端聚合；新鲜度/延迟/错误率的计算全在后端。
- 流式徽章只反映 `openEventStream` 状态（store `streamingActive`），
  不新增客户端测量。

## 4. Files to create/modify

- modify `clients/web/src/api/client.ts`
  - `PipelineHealthSourceDTO`、`PipelineHealthDTO`、`api.pipelineHealth()`
- modify `clients/web/src/stores/api.ts`
  - `pipelineHealth` 状态；`fetchWorkspace` 拉取；`refreshMonitoring` 一并刷新
    （沿用既有 10s/SSE 节拍）
- modify `clients/web/src/components/RuntimeWorkspace.tsx`
  - props 增 `pipelineHealth`、`onRefreshHealth`；新增管线健康面板
- modify `clients/web/src/app/workspaces/WorkspaceRenderer.tsx`（传 props）
- modify `clients/web/src/components/WorkspaceTopBar.tsx`
  - props 增 `streamingActive: boolean`；status 徽章旁新增流式模式徽章
- modify `clients/web/src/app/shell/AppShell.tsx`（传 `streamingActive`）
- modify `clients/web/src/i18n/en.json` + `zh.json`（runtime./stream. 新 key）
- modify `clients/web/src/styles/app.css`（面板/徽章少量样式）
- modify `tests/contract/test_trader_client_correctness.py`（断言：Runtime 面板
  消费 pipelineHealth；顶栏消费 streamingActive；双语 key）

## 5. Dependency policy

零新依赖。

## 6. Data policy

只读；无本地持久化。

## 7. API impact

无后端变更。

## 8. DB impact

无。

## 9. Tests

- 契约测试新增断言；既有契约测试保持全绿。
- `tsc --noEmit` + vite build。

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

- Runtime 工作区显示每源状态/失败计数/最近成功、报价新鲜度、开放告警、最新机会。
- 顶栏徽章在 SSE 可用时显示「实时推送」，断开时显示「轮询兜底」。
- 契约测试 + tsc + build 全绿；假数据 pipeline 零 diff。

## 12. Rollback notes

- 纯前端增量；`git revert` 即回退。
