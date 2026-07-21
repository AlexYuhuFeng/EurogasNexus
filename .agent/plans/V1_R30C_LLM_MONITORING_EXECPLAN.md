# V1 R30C - Visible LLM Monitoring and Interaction

Status: `complete-in-current-worktree`

## 1. Goal

Deliver a DB-first monitoring layer that continuously normalizes market,
strategy, source, and runtime conditions into visible alerts. Deterministic
engines remain the source of alert truth. DeepSeek may enrich an alert with a
governed explanation and may answer user questions about the persisted alert
context.

## 2. Non-goals

- No order entry, routing, execution, nomination, approval, or auto-trading.
- No LLM-generated alert trigger or autonomous commercial action.
- No browser or desktop direct access to PostgreSQL or provider credentials.
- No Kafka, Redis, Celery, websocket infrastructure, or new heavy dependency.
- No live provider call from import-time code or automated tests.

## 3. Product boundary

Alerts are decision-support evidence and require human review. The deterministic
monitoring service detects conditions and records lineage. DeepSeek only
summarizes supplied database snapshots. The system must continue generating and
displaying alerts when DeepSeek is unconfigured or unavailable.

## 4. Files to create or modify

- Add a monitoring SQLAlchemy model and Alembic revision.
- Add monitoring repository/service and a bounded periodic worker script.
- Add public monitoring read, acknowledgement, and contextual analysis routes.
- Refactor DeepSeek invocation into a backend-owned provider adapter.
- Extend the credential API with a non-disclosing DeepSeek connection test.
- Register monitoring tables and routes.
- Add the monitoring worker to the Docker runtime and installation lifecycle.
- Add typed Web API/store support and a top-bar alert center.
- Add bilingual operations and user documentation.
- Add API, unit, integration, client-contract, release, and security tests.

## 5. Dependency policy

Use the existing FastAPI, Pydantic, SQLAlchemy, Alembic, HTTPX, React,
TypeScript, Zustand, and Tauri stack. Add no dependency.

## 6. Data policy

PostgreSQL is the source of truth for normalized alerts, acknowledgement,
lineage, context, and LLM enrichment status. API keys remain encrypted in
`provider_credentials`; API responses and logs never return them. Simulated
quotes remain explicitly marked and produce simulated alerts.

## 7. API impact

Add stable unversioned routes:

- `GET /api/monitoring/alerts`
- `GET /api/monitoring/summary`
- `POST /api/monitoring/alerts/{alert_id}/acknowledge`
- `POST /api/monitoring/alerts/{alert_id}/analysis`
- `POST /api/credentials/{provider_id}/connection-test`

No `/v1` or `/api/v1` aliases.

## 8. DB impact

Add `monitoring_alerts` with a stable fingerprint, lifecycle status, bilingual
deterministic copy, evidence snapshot, source references, warnings, simulated
flag, acknowledgement timestamps, and DeepSeek enrichment fields. The worker
upserts by fingerprint and resolves conditions that are no longer active.

## 9. Tests

- Migration/model/registry contract tests.
- Deterministic alert normalization and deduplication tests.
- API list, summary, acknowledgement, and alert-analysis tests.
- DeepSeek success/failure/missing-key tests with HTTPX mocked.
- Credential connection test redaction tests.
- Client API/store/top-bar contract tests.
- Runtime Compose worker contract tests.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
npm run build --prefix clients/web
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Alerts persist in PostgreSQL and remain available when DeepSeek is down.
- New opportunity, strategy, and source-failure conditions are deduplicated.
- The client refreshes alerts every 10 seconds from `/api`.
- Users can see severity/unread state, acknowledge an alert, and ask DeepSeek
  about the selected alert without exposing the API key.
- DeepSeek enrichment is visibly labelled configured, missing, success, or
  failed and includes source references and human-review requirements.
- AllInOne and Server runtime start the monitoring worker after migrations.
- Tests never contact DeepSeek.

Completion evidence: the official DeepSeek API returned `success` for an
explicit connection test, three DB-backed alert enrichments, and one per-alert
interactive analysis. The supplied test credential was not committed or logged
and its temporary encrypted database row was removed after validation.

## 12. Rollback notes

Stop the `monitoring-worker` service, remove the monitoring router and client
surface, and downgrade revision `0015_llm_monitoring_alerts`. Existing market,
strategy, source, credential, and analysis tables remain unchanged.
