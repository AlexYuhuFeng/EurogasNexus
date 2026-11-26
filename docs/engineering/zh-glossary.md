# Chinese (zh) glossary for the desk

The terms the Chinese interface and the Chinese reports use, chosen for a Chinese-speaking gas
and LNG trader. `clients/web/src/i18n/zh.json` and the report strings in
`src/eurogas_nexus/application/reports/` follow this list; a new string uses these terms.

## Rules

- Hub codes, product codes and contract terms stay in Latin: TTF, NBP, THE, PEG, ZTP, PSV, PVB,
  Dec-26, Q1-27, Sum-27, Cal-27, DES, FOB, WD/DA where the English shows the code. Henry Hub is
  a name and stays in Latin as well (never 亨利港, which reads as a port).
- One space between a Latin word and Chinese text (`LNG 船货`, `Henry Hub 价格`).
- Keys and `{{placeholders}}` never change; only values do.

## Terms

| English | Chinese | Not |
|---|---|---|
| cargo (LNG cargo) | 船货 / LNG 船货 | 货物 (goods) |
| Cargo & netback (page) | LNG 船货与净回值 | 货物与净回值 |
| netback | 净回值 | |
| cost at the ship's rail (delivered cost) | 卸港到岸成本 | 船舷成本 |
| DES / FOB | DES / FOB | |
| send-out | 外输 | 气化外输 |
| regasification, regas slot | 再气化, 再气化窗口 | 气化, 气化窗口 |
| regas tariff | 再气化费 | 再气化费率 |
| boil-off, boil-off rate | 蒸发气（BOG）, BOG 率, BOG 损耗 | 蒸发损耗, 蒸发率 |
| nomination | 提名 | 申报 |
| allocation | 分配 | |
| imbalance | 不平衡 | |
| gas day | 燃气日 | 气日, 气体日, 天然气日 |
| hub | 枢纽 | 中心 |
| spread | 价差 | |
| mark-to-market | 盯市 | |
| P&L, PnL | 损益 | 盈亏, PnL in Chinese text |
| mandate (trader mandate) | 交易授权 | 授权 alone, which also means a data licence |
| licensed (data) | 授权（数据） | |
| credit line | 信用额度 | 授信额度, 授信 |
| outage | 停运 / 检修 | |
| entry / exit capacity | 入口容量 / 出口容量 | 入口能力, 进出容量 |
| storage injection / withdrawal | 注气 / 采气 (储气库注气, 储气库采气) | 储气注入, 储气采出, 提取 |
| desk (trading desk) | 交易台 | 桌面 (desktop) |
| within-day, day-ahead | 日内, 日前 | |

## Main changes (2026-11-26, 153 values on main)

- 23 "cargo" strings said 货物 or 货船 (cargo ship); they say 船货 (LNG 船货 where the English says LNG cargo).
- 28 Henry Hub strings said 亨利港 or 亨利中心; they say Henry Hub. Three values are now the
  same as English and are declared in `tests/localeDistinctness.test.ts`.
- Gas day was written four ways (燃气日, 气日, 气体日, 天然气日; 21 values); it is 燃气日 everywhere,
  the report renderer and its glossary included.
- 盈亏 and the Latin PnL inside Chinese text are 损益.
- Mandate strings say 交易授权, so a mandate breach no longer reads like a licence problem.
- 授信额度 is 信用额度; 入口能力 is 入口容量; 申报 is 提名 for nominations.
- Boil-off is 蒸发气（BOG） and BOG 率; send-out is 外输; 气化窗口 is 再气化窗口.
- "Desk standard" said 桌面标准 (desktop standard); it says 交易台标准.
- The cargo cost line said 船舷成本; it says 卸港到岸成本.
- Wrong translations: the third Spreads example said 德国对荷兰 次月 历史 for "NBP to PEG
  forward spread net of transport"; the NBP vs TTF examples named countries (英国对荷兰) instead
  of the hubs. They now name the hubs and read the same spread the English does (the Spreads
  reader parses them, checked).
