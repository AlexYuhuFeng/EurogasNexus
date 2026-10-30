# Architecture

One backend, one database, several clients. Every client and integration goes through the
backend API (`/api`); nothing but the backend reads or writes PostgreSQL. Decisions behind
this shape are recorded in [ARCHITECTURE_DECISION_RECORD.md](ARCHITECTURE_DECISION_RECORD.md);
the multi-office topology is in [GLOBAL_DEPLOYMENT.md](GLOBAL_DEPLOYMENT.md).

```
 Web (React)   Desktop (Tauri: Windows, Linux)   Python SDK / CLI   MCP tools
        \               |                              |              /
         └──────────────┴────────── HTTPS /api ────────┴─────────────┘
                                     │
                       FastAPI application (apps/api)
      security · routes · projections · application services · domain · LLM adapter
                                     │
          PostgreSQL (Alembic migrations)        workers: data-ops scheduler,
          runtime truth, audit, research          ingestion scripts, monitoring,
          artefacts metadata                      shadow scheduler
                                     │
      External sources: ENTSOG, GIE, ECB, BoE, NY Fed, ECMWF, National Gas, ENTSO-E,
      EEX public file; licensed feeds through the customer's own entitlement
```

## Backend packages (`src/eurogas_nexus`)

| Package | Owns | Depends on |
|---|---|---|
| `core` | Settings, configuration contract, shared primitives | nothing in the product |
| `domain` | Pure business logic: gas day and products, units, route costs, spreads, forward curve, research datasets and features, power fundamentals, portfolio ladder, settings rules | `core` |
| `optimization` | Resource-pool, capacity and storage optimisation | `domain` |
| `ingestion` | Parsers and transports for each source; no analysis | `domain`, `core` |
| `db` | SQLAlchemy models and repositories | `domain`, `core` |
| `application` | Services that compose domain logic with storage: projections, data operations, research registry, decision packs, shadow runtime | `domain`, `db` |
| `security` | Identity, RBAC permissions, data scopes, capabilities, OIDC | `core`, `db` |
| `governance` | Audit and policy evaluation | `db` |
| `api` | HTTP routes, dependencies, error envelope, route registration | everything above |
| `llm` | Provider-neutral chat-completions adapter (advisory only) | `core` |
| `mcp`, `cli` | Agent tools and command line, both as API consumers | `api` client side |
| `streaming`, `runtime_store`, `data_quality`, `release` | Server-sent events, store wiring, quality checks, release identity | as named |

Rules that keep this healthy (tested in `tests/contract`):

- Domain code imports no web, database or network library.
- Clients name no vendor endpoint; vendor hosts appear only in ingestion and the LLM adapter.
- Every public route declares a permission, is pinned in the surface census, and is reached
  by a client or the SDK.
- Work mode and job function shape the interface only; roles and data scopes grant access.

## Data flow

1. **Ingest:** a source adapter fetches and parses into typed observations with source
   reference, units and availability time. Licensed families are stored under the
   customer's entitlement; simulated sources are marked and never shown as market prices.
2. **Store:** observations, contracts, positions, research artefacts and audit events in
   PostgreSQL, indexed by entity and time.
3. **Read:** projections batch what a workspace needs in one request; every row passes the
   caller's data scopes.
4. **Analyse:** spread lab, backtests, position ladder, route economics, weather-demand and
   gas-for-power calculations, and point-in-time datasets for model training run in the
   backend and return provenance and warnings with the numbers.
5. **Decide:** decision cases collect evidence for human review (four-eyes). Nothing places
   orders, nominates or settles.

## Clients (`clients/`)

- `web`: React and TypeScript. `app/model` holds pure, tested logic; `components` render it;
  `api/client.ts` is the only HTTP entry point; `i18n` holds the locale registry and
  translations.
- `desktop`: Tauri 2 shell around the same web build, `core:default` permissions only.
- `packages/python-sdk`: typed client for analysts and quants.

## Quality gates

`scripts/ci/pre_push_check.sh` runs the fast gates locally. CI adds PostgreSQL migrations
and integration tests, whole-product browser acceptance in English and Chinese with
accessibility checks, native desktop builds, SDK wheel acceptance, numerical acceptance
for the weather model, and licence and vulnerability audits. See
[CI_AND_BRANCH_PROTECTION.md](../engineering/CI_AND_BRANCH_PROTECTION.md).
