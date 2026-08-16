# F4: Source Center 认证门展示 ExecPlan

## 1. Goal

把 S4.2 的 provider 认证门展示到 Sources 工作区：
- licensed 源显示认证阶段徽章（`unverified` / `simulation_matched` /
  `live_validated`）；
- 有记录但未认证的源（后端 `operational_status="active_uncertified"`）
  以「需要认证」的关注态展示，下一动作指向 `certify`；
- 详情面板展示 `certification_stage` / `certification_allows_live`。

## 2. Non-goals

- 不改后端（`/api/sources` 已含 `certification_stage`/
  `certification_allows_live`/`active_uncertified`）。
- 不在前端提供认证写入（认证走 internal operator 端点，非公开 UI 能力）。
- 零新依赖；假数据 pipeline 零 diff；不碰 `GasNetworkMap`。

## 3. Product boundary

- 客户端只读展示后端 fail-closed 判定；不重复实现门逻辑。

## 4. Files to create/modify

- modify `clients/web/src/api/client.ts`
  - `SourceSystemDTO` + `SourceSystemWire` + `normalizeSourceSystem` 增加
    `certification_stage` / `certification_allows_live`
- modify `clients/web/src/app/workspaceDerivedData.ts`
  - `sourceNextActionKey`：`operational_status === "active_uncertified"` →
    `sources.action.certify`
- modify `clients/web/src/components/SourceCenter.tsx`
  - 运营表 licensed 行加认证徽章；详情面板加认证指标行
- modify `clients/web/src/i18n/en.json` + `zh.json`
- modify `clients/web/src/styles/app.css`（认证徽章样式）
- modify `tests/contract/test_trader_client_correctness.py`（断言认证字段消费）

## 5. Dependency policy

零新依赖。

## 6. Data policy

只读；无本地持久化。

## 7. API impact

无后端变更。

## 8. DB impact

无。

## 9. Tests

- 契约测试新增断言；既有契约测试全绿；`tsc` + vite build。

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

- Sources 列表可见 licensed 源认证阶段；未认证 active 源显示关注态与
  `certify` 下一动作；详情面板含认证指标。
- 契约测试 + tsc + build 全绿；假数据 pipeline 零 diff。

## 12. Rollback notes

- 纯前端增量；`git revert` 即回退。
