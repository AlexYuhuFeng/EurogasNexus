# API/SDK/MCP Completeness — ExecPlan (P1→P3)

> **Status: COMPLETE (2026 session round 9).** P1/P2/P3 all landed with
> tests; final validation: `pytest` 923 passed + 4 skipped (postgres smoke),
> `ruff check` clean, MCP stdio handshake verified end-to-end. Remaining
> environment-dependent acceptance (CI pip-audit first run, PG16 smoke first
> run) is tracked in ci.yml jobs.

User directive (2026 session continuation): close the API/SDK/MCP coverage
gaps identified in the completeness review. The review established: API layer
is solid; SDK lacks clients for `/api/optimization/*` (incl. run evidence),
`/api/review/decisions`, and `/api/credentials/providers`; CLI has only 12
commands; SSE has no Python client; no MCP server exists; API pagination and
error-detail shapes are not fully uniform.

## 1. Goal

1. P1 — SDK clients for optimization (route/resource-pool/capacity/contracts
   + `runs/{run_id}` evidence), review decisions (read + record), and
   credential providers (read-only), with drift-prevention parity tests.
2. P2 — CLI subcommands for the new SDK surface (optimization/analysis/
   sources/review), and an SSE streaming client with `Last-Event-ID` resume.
3. P3 — a read-only MCP server implemented with stdlib JSON-RPC 2.0 over
   stdio (no new dependency), exposing ontology/glossary/market/route-cost/
   review-evidence tools that reuse the SDK and therefore the release auth
   gates; plus API pagination/error-detail convergence.

## 2. Non-goals

- Credential writes via SDK (operator-only routes stay operator-only).
- MCP tools that mutate state, call external LLMs, or bypass API auth.
- Web client changes beyond the existing review evidence panel.
- New third-party dependencies (fastmcp, etc.) unless a separate ExecPlan
  approves them.

## 3. Product boundary

Decision support only. SDK/CLI/MCP are read-side consumers; MCP exposes no
write tools and no external-provider invocation.

## 4. Files

Create:
- `src/eurogas_nexus/sdk/optimization.py`
- `src/eurogas_nexus/sdk/review.py`
- `src/eurogas_nexus/sdk/credentials.py`
- `src/eurogas_nexus/sdk/streaming.py`
- `src/eurogas_nexus/mcp/__init__.py`, `src/eurogas_nexus/mcp/server.py`
- `tests/sdk/test_optimization_client.py`, `test_review_client.py`,
  `test_credentials_client.py`, `test_streaming_client.py`
- `tests/unit/test_mcp_server.py`
- `.agent/plans/SDK_MCP_COMPLETENESS_EXECPLAN.md` (this file)

Modify:
- `src/eurogas_nexus/cli/main.py`, `src/eurogas_nexus/cli/commands.py`
- `tests/contract/test_sdk_backend_parity.py`
- `tests/cli/test_main.py`
- `.github/workflows/ci.yml` (MCP smoke step)

## 5. Dependency policy

No new third-party dependencies. MCP uses stdlib `json`/`asyncio`/stdio
(JSON-RPC 2.0 wire format, the documented MCP stdio transport).

## 6. Data policy

MCP tools call the local API through the SDK; they never open the DB, never
accept secrets, and never trigger provider/LLM calls.

## 7. API impact

None (additive clients). API convergence (P3b): normalize list endpoints to
`limit`/`offset` where trivially additive; keep error-detail `code` convention
documented.

## 8. DB impact

None.

## 9. Tests

- SDK clients with monkeypatched HTTP fakes (existing pattern).
- Parity: SDK DTO fields ⊆ backend payload keys (optimization results,
  optimization runs, review decisions, credential providers).
- CLI: new subcommands + BLOCKED exit code semantics.
- MCP: initialize/list-tools/call-tools over an in-process stdio pair;
  unknown tool and auth-failure cases.

## 10. Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/unit tests/sdk tests/cli tests/security
python -c "from apps.api.main import app; print('app import ok')"
cd clients/web && node .\node_modules\typescript\bin\tsc --noEmit
```

## 11. Acceptance criteria

- Every `/api/optimization/*` path and `/api/review/*` + credentials read has
  an SDK function; parity tests fail on drift.
- CLI exposes optimization + review + analysis + sources commands with exit
  codes 0/1/2.
- MCP server answers `initialize`, `tools/list`, `tools/call` for read-only
  tools over stdio, with no new dependency and no write paths.

## 12. Rollback

Revert this plan's commits; SDK/CLI/MCP are additive. MCP server removal
restores prior behavior; no migration involved.
