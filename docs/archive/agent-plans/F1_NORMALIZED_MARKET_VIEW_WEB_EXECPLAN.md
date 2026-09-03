# F1: 前端数据面下沉（规范化市场视图消费）ExecPlan

## 1. Goal

把前端对 FX/tenor/hub/spread 的全部客户端重实现删除，改消费后端
`GET /api/market/normalized` 与 `GET /api/market/spreads`。落地路线图 S3.3
的前端部分与问题 P2，让「交易员看到的数字」与后端逐字节一致。

## 2. Non-goals

- 不改后端结构。执行中按既定原则做了一处 **additive** 后端补充：发现
  `/api/market/spreads` 只有 `from_venue`/`to_venue`，前端按 hub 匹配只能
  脆解析 `name` 字符串（正是要消灭的双解释模式），故为该端点与 SDK DTO
  增加 `from_hub`/`to_hub` 字段（既有字段不变、路径数不变）。
- 不动 `GasNetworkMap.tsx`（用户未提交 WIP）与其他无关工作区。
- 不新增任何前端依赖（不加测试框架/请求库）。
- 不把「SAP/ICIS/OCM 行挑选」场景组装逻辑后端化（那是 R31 范畴）。
- 假数据 pipeline 零 diff。

## 3. Product boundary

- 客户端 = 薄消费者：`hub`/`tenor`/`is_gas_price`/`price_gbp_mwh` 只从后端行读取；
  客户端源码里禁止出现汇率图构建（`buildLatestCurrencyGraph`）、`1 / rate` 反向
  汇率、hub/tenor 字符串解析、`latest.price - ttfLatest.price` 价差数学。
- `fxRates` 保留在 store：仅用于 FX 展示与新鲜度检查，不再参与任何换算。
- 场景组装（`buildStrategyScenario`）保留在前端，但只在规范化行上做
  过滤/排序/取最新，不产生任何派生价格。

## 4. Files to create/modify

- modify `clients/web/src/api/client.ts`
  - `NormalizedMarketObsDTO extends MarketObsDTO`（+`hub`/`tenor`/`is_gas_price`/
    `price_gbp_mwh: number | null`）、`MarketSpreadDTO`（spread_id/name/
    from_venue/to_venue/spread_eur_mwh/period）
  - `api.normalizedMarketObservations()`（`/market/normalized`）、
    `api.marketSpreads()`（`/market/spreads`）
- delete `clients/web/src/app/marketPriceNormalization.ts`
- modify `clients/web/src/app/index.ts`（移除 5 个 normalization 导出）
- modify `clients/web/src/stores/api.ts`
  - `markets: MarketObsDTO[]` → `normalizedMarkets: NormalizedMarketObsDTO[]`
  - 新增 `marketSpreads: MarketSpreadDTO[]`
  - `fetchWorkspace` / `refreshMarketData`：改拉 `/market/normalized` 与
    `/market/spreads`；`fxRates` 继续拉（展示/新鲜度用）
- modify `clients/web/src/app/strategyScenario.ts`
  - 签名去 `fxRates`；`price_gbp_mwh = row.price_gbp_mwh`；hub/tenor 读行字段；
    过滤条件 `row.is_gas_price && row.price_gbp_mwh != null && > 0`
- modify `clients/web/src/components/StrategyShadowRunTerminal.tsx`
  - `tapePriceFromMarketObservation` 改读 `item.is_gas_price`/
    `item.price_gbp_mwh`/`item.hub`；`fxRates` 仅留新鲜度用途
- modify `clients/web/src/components/MarketTerminal.tsx`
  - 删除本地 `marketTenor`/`isGasMarketObservation`/`hubForObservation` 重实现，
    改读 `row.tenor`/`row.is_gas_price`/`row.hub`（major-hub 过滤保留为展示过滤）
  - `spreadToTtf` 改从后端 `marketSpreads` 匹配（`<hub> -> TTF`/`TTF -> <hub>`
    同 period 行，反向取负）；无后端价差时显式 `null`，不再客户端相减
- modify `clients/web/src/app/model/usePortfolioDecisionModel.ts`
  - `contextMarkets`/`buildStrategyScenario` 改用 `normalizedMarkets`，去 `fxRates`
- modify `tests/contract/test_trader_client_correctness.py`
  - `test_strategy_prices_are_currency_normalized_and_not_zero_fallbacks` 重写为
    `test_strategy_prices_consume_backend_normalized_market_view`：
    断言 `marketPriceNormalization.ts` 不存在；scenario/terminal 读
    `price_gbp_mwh`/`is_gas_price`；全仓 `clients/web/src` 无
    `buildLatestCurrencyGraph`、无 `1 / rate`、无 `latest.price - ttfLatest.price`
  - 其余测试同步（`api.fxRates` 断言改为 `api.normalizedMarketObservations` 等）
- modify `clients/web/src/i18n/{en,zh}.json`（仅当出现新文案时；尽量复用现有 key）

## 5. Dependency policy

零新依赖。React/Vite/zustand/maplibre 现状不动。

## 6. Data policy

- 客户端不再产出任何派生价格/汇率/价差；所有数值来自后端行或用户输入。
- 后端未给出价差的地方显示空（诚实），不本地补算。

## 7. API impact

无后端变更。客户端改为消费既有 `/api/market/normalized`、`/api/market/spreads`。

## 8. DB impact

无。

## 9. Tests

- 契约测试（重写后）：
  - 归一化文件已删除；
  - store 拉 `/market/normalized` 与 `/market/spreads`；
  - 客户端源码禁止汇率图/反向汇率/hub-tenor 解析/价差相减模式；
  - strategyScenario/terminal 消费 `price_gbp_mwh`；
  - 既有 i18n 双语 key 测试、tradingContext 过滤测试保持全绿。
- `tsc --noEmit`（`node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json`，workdir `clients/web`）+ vite build 通过。

## 10. Validation commands

```powershell
# backend contracts (unchanged, keep green)
$env:PYTHONPATH = "$PWD\.deps;$PWD\src"
python -m pytest tests/contract/test_trader_client_correctness.py tests/contract -q -p no:cacheprovider
# web typecheck + build
node node_modules/typescript/bin/tsc --noEmit -p tsconfig.json   # workdir clients/web
node node_modules/vite/bin/vite.js build                            # workdir clients/web
# fake pipeline untouched
git status --porcelain -- src/eurogas_nexus/ingestion scripts/ops/ingest_simulated_market_prices.py scripts/ops/seed_preview_runtime_data.py
```

## 11. Acceptance criteria

- `marketPriceNormalization.ts` 从仓库消失；`clients/web/src` 无任何汇率/价差数学。
- Strategy 场景与 tape 价格读后端 `price_gbp_mwh`；Market 终端价差来自后端或显式空。
- 契约测试 + tsc + vite build 全绿；假数据 pipeline 零 diff；后端 90 路径不变。
- 行为对照：同一仿真数据集上，`buildStrategyScenario` 输出与改造前一致
  （SAP/ICIS/OCM 挑选结果不变；无法自动断言的部分在交付说明中列出手动核对点）。

## 12. Rollback notes

- 纯前端变更：`git revert` 该提交即回退；后端端点保留无影响。
- 前端无新状态表/无新依赖，回退零残留。
