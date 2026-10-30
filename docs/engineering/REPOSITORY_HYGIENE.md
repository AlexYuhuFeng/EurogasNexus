# Repository hygiene assessment (2026-10-30)

## Size is not the problem

About 1,900 tracked files: tests 475, backend 427, clients 394, docs 339, scripts 109,
migrations 49. That is in line with a product that ships a FastAPI backend, a React web
client, a Tauri desktop shell, a Python SDK, release tooling and its own acceptance
evidence. No generated output (`dist/`, `__pycache__`, `*.egg-info`, `node_modules`),
logs or large binaries are tracked; the only binaries are desktop icons. Deleting files to
reduce the count would remove tests or evidence, so it is not recommended.

## What does need work

| Item | Problem | Plan |
|---|---|---|
| `docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md` | 374 KB log every agent must read | **Done:** rotated to `history/`; rotate again past ~500 lines |
| `clients/web/src/api/client.ts` (177 KB) | One file for every DTO and endpoint | Split by domain (`api/market.ts`, `api/research.ts`, …) re-exported from `api/client.ts`, one domain per change |
| `clients/web/src/styles/app.css` (195 KB) | Global stylesheet; a legacy rule broke SVG charts | Move rules next to their component (as `strategy-lab.css` and `WorkspaceTopBar.css` already are); keep only tokens and layout globally |
| `clients/web/src/stores/api.ts` (110 KB) | One store for every read | Split per workspace, following the projections |
| `src/eurogas_nexus/domain/research/weather_demand.py` (154 KB) | Model, features and evidence in one module | Split into features, fit and evidence modules behind the same public functions |
| `docs/engineering/Architecture-V2/` (44 wave records) | Closed plans read as current | Mark each *Closed* with a link to the owning document (DOCUMENTATION_POLICY.md) |

Each split is a refactor with no behaviour change: the existing tests must pass unchanged,
and source-pin tests that name a file move with it.
