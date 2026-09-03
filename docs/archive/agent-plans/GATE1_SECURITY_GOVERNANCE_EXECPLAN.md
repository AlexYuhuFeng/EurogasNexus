# Gate 1: Security & Data Governance — ExecPlan

Continuation of the Sol 5.6 remediation (Gate 0 shipped). Scope: request-ID
traceability, durable audit events for policy decisions, export/egress policy on
report generation, and LLM payload field filtering. Full user auth/roles and
row-level entitlement remain deferred (documented in the audit's Gate 1 list).

## 1. Goal

1. Every HTTP response carries `X-Request-Id`; policy decisions (entitlement
   denials, export denials, LLM invocations, review decisions) are recorded as
   immutable `audit_events` rows with request context when the runtime DB is
   available.
2. Report generation fails closed when the snapshot contains data whose
   entitlement scope is UNKNOWN (export policy).
3. LLM calls receive a filtered snapshot: contract financial fields are
   excluded unless the client explicitly opts in (`include_contract_prices`).

## 2. Non-goals

- Full user accounts, roles, sessions, SSO/OIDC (later Gate 1 milestone).
- Row-level (per-instance) entitlement enforcement across every read route.
- Audit log rotation/retention policy (operations milestone).

## 3. Product boundary

Decision support only. Audit events are append-only records, never used to
authorize anything; policy decisions stay fail-closed for unknown data.

## 4. Files

Create:
- `src/eurogas_nexus/api/middleware/request_id.py`
- `src/eurogas_nexus/application/audit_service.py`
- `tests/api/test_request_id_middleware.py`
- `tests/unit/test_audit_service.py`

Modify:
- `src/eurogas_nexus/api/app.py` (middleware registration)
- `src/eurogas_nexus/api/routes/public/analysis.py` (export gate, audit events,
  LLM payload filter)
- `src/eurogas_nexus/api/routes/public/review.py` (audit event on decision)
- `src/eurogas_nexus/domain/analysis.py` (AnalysisRequest.include_contract_prices)
- `tests/api/test_analysis_api.py`, `tests/api/test_review_api.py`

## 5. Dependency policy

No new dependencies; stdlib `uuid` and existing FastAPI/SQLAlchemy only.

## 6. Data policy

Audit writes are best-effort: DB unavailable -> skip silently (the API already
reports runtime-db state). Never log secret values (API keys, tokens).

## 7. API impact

- All responses gain `X-Request-Id` (uuid, short form).
- `POST /api/reports/portfolio` returns 403 `export_denied` when snapshot
  sources evaluate to UNKNOWN entitlement scope.
- `POST /api/analysis/query` accepts `include_contract_prices: bool = false`;
  when false, LLM payload excludes contract financial fields and the result
  carries warning `LLM_PAYLOAD_FILTERED:contract_prices`.

## 8. DB impact

No schema change; uses existing `audit_events` table.

## 9. Tests

- Middleware: X-Request-Id present; stable across route handler; no id for
  non-HTTP scopes (unit-level).
- Audit service: writes row when DB configured (SQLite), no-op when not.
- Export gate: unknown-scope snapshot -> 403; empty snapshot -> 200.
- LLM filter: payload excludes `contract_price_gbp_mwh` by default; warning
  added; opt-in includes them.

## 10. Validation

```powershell
ruff check .
pytest -q tests/api tests/unit tests/security tests/contract
python -c "from apps.api.main import app; print('app import ok')"
```

## 11. Acceptance criteria

- Every response header includes X-Request-Id.
- Entitlement/export denials and review decisions produce audit_events rows
  (verified against SQLite in tests).
- Unknown-scope report generation is blocked with 403.
- LLM provider payload never contains contract prices by default.

## 12. Rollback

Revert this milestone's commits; no migration involved. Middleware removal
restores previous header behavior; audit/export changes are additive checks.
