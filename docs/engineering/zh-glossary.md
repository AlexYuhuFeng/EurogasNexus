# Chinese (zh) glossary for the desk

The Chinese interface and the Chinese reports use one fixed set of terms, chosen for a
Chinese-speaking gas and LNG trader. The term table, with the wrong renderings each term
replaces, is the Chinese companion `zh-glossary-CN.md`. `clients/web/src/i18n/zh.json` and the
report strings in `src/eurogas_nexus/application/reports/` follow it, and a new string uses
those terms.

## Rules

- Hub codes, product codes and contract terms stay in Latin script: TTF, NBP, THE, PEG, ZTP,
  PSV, PVB, Dec-26, Q1-27, Sum-27, Cal-27, DES, FOB, WD/DA where the English shows the code.
- Henry Hub is a name and stays in Latin script, as Chinese market reports usually write it.
  A Chinese rendering that reads as a port is wrong.
- One space between a Latin word and Chinese text.
- Keys and `{{placeholders}}` never change; only values do.
- One term per concept: "cargo" is always the LNG-cargo term (never the word for goods or
  for a cargo ship), "gas day" has one rendering everywhere, P&L has one rendering and never
  the Latin "PnL" inside Chinese text, and a trader mandate has its own term so that a
  mandate breach does not read like a data-licence problem.

## Main changes (2026-11-26, 197 values on this branch)

- Cargo strings, including the LNG disruption and cargo-fix strings, use the LNG-cargo term.
- 28 Henry Hub strings used a Chinese rendering; they say Henry Hub. Three values are now the
  same as English and are declared in `tests/localeDistinctness.test.ts`.
- Gas day was written four ways (21 values); it has one rendering everywhere, the report
  renderer and its glossary included.
- P&L, mandate, credit line, entry capacity, nomination, boil-off, send-out, regas slot,
  "desk standard" and the cargo cost line each use the glossary term.
- The Spreads examples now name the hubs, not countries, and read the same spread as the
  English (the Spreads reader parses them, checked).
