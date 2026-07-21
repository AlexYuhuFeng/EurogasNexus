# DeepSeek Live Monitoring and Interaction

## Purpose

Eurogas Nexus uses DeepSeek as a governed analysis layer over deterministic,
PostgreSQL-backed monitoring events. DeepSeek does not discover spreads, decide
capacity feasibility, calculate route cost, or execute business actions. Those
results remain owned by the market, route, strategy, ingestion, and risk engines.

The V1 provider configuration is fixed to **DeepSeek V4 Flash** with API model
ID `deepseek-v4-flash`. The backend uses `https://api.deepseek.com` and its
OpenAI-compatible Chat Completions endpoint. Clients cannot override the model
or provider base URL.

The live workflow is absolute:

1. Backend engines persist quotes, opportunities, strategy alerts, ingestion
   runs, source evidence, assumptions, and warnings in PostgreSQL.
2. `monitoring-worker` scans the database every 10 seconds.
3. It normalizes active conditions into `monitoring_alerts` using a stable
   fingerprint.
4. A new, returned, or severity-escalated alert may be enriched by the live
   DeepSeek API.
5. Web and desktop clients poll the monitoring API every 10 seconds and display
   the persisted alert in the top-bar Alert Center.
6. A user can acknowledge an alert or ask DeepSeek a follow-up question. The
   question is sent only when the user presses **Send**.

All business actions remain human-reviewed. The LLM cannot place orders, submit
nominations, book capacity, approve contracts, or alter source data.

## Configure the DeepSeek Key

Internet access to `https://api.deepseek.com` is required for live LLM use.
The API, PostgreSQL, and `monitoring-worker` must be running.

1. Open **Workspace > Operations > Data Sources**.
2. Select the **LLM** category and **DeepSeek LLM** source.
3. Select provider `DEEPSEEK`.
4. Enter a non-secret label such as `operator-default`.
5. Enter the customer's DeepSeek API key in the password field.
6. Select **Save credential**.
7. Select **Test live connection**.
8. Confirm the status changes to `connection_test_success`.

The client sends the value once to the backend. The backend encrypts it before
writing it to `provider_credentials`. The API returns only a redacted preview and
test status. The key must never be added to `.env` files committed to Git, shell
history, screenshots, reports, support tickets, or client local storage.

`EUROGAS_NEXUS_SECRET_KEY` protects stored provider credentials and is generated
for AllInOne/Server installation. Losing this encryption key makes existing
credential rows unusable; rotate provider keys after restoring the runtime.

## Runtime Calls and Cost Control

The worker does not call DeepSeek every 10 seconds for the same condition.

- New alert: one enrichment request.
- Same alert and severity: no new enrichment request.
- Severity increase: one new enrichment request.
- Resolved alert that returns: one new enrichment request.
- Failed provider request: retry no sooner than five minutes.
- Per worker scan: at most three enrichment requests.
- User follow-up: exactly one request when **Send** is selected.
- Portfolio report or Review question: exactly one request when its explicit
  DeepSeek option is submitted.

The stable fingerprint excludes quote IDs and scan IDs so a continuously
recalculated spread does not create a new alert every tick.

## Visible Status

The top-bar Alert Center displays:

- open, acknowledged, and severity counts;
- deterministic bilingual title and evidence summary;
- source category, last update, occurrence count, and simulated-input marker;
- DeepSeek enrichment status and bilingual explanation;
- acknowledgement control;
- a per-alert DeepSeek discussion field.

Expected LLM states:

| State | Meaning | Operator action |
| --- | --- | --- |
| `success` | DeepSeek returned a valid response. | Review it against cited evidence. |
| `pending` | A new/escalated alert awaits enrichment. | Wait for the worker cycle. |
| `missing_credential` | No enabled DeepSeek/LLM key can be decrypted. | Save and test a key in Data Sources. |
| `provider_http_error` | DeepSeek rejected or rate-limited the call. | Check account status, entitlement, and provider service. |
| `provider_call_failed` | Network, timeout, or response parsing failed. | Diagnose outbound HTTPS/DNS and retry after five minutes. |

Source ingestion alerts are escalated from warning to critical after three
consecutive failed runs. Market opportunity and strategy alert facts always come
from deterministic runtime records, even when DeepSeek is unavailable.

## API

Clients use the stable `/api` surface:

- `GET /api/monitoring/alerts`
- `GET /api/monitoring/summary`
- `POST /api/monitoring/alerts/{alert_id}/acknowledge`
- `POST /api/monitoring/alerts/{alert_id}/analysis`
- `POST /api/credentials/DEEPSEEK/connection-test`
- `POST /api/analysis/query`
- `POST /api/reports/portfolio`

No client accesses PostgreSQL or DeepSeek directly.

Python SDK users import from `eurogas_nexus.sdk.monitoring`:

```python
from eurogas_nexus.sdk.monitoring import (
    analyze_monitoring_alert,
    fetch_monitoring_alerts,
    fetch_monitoring_summary,
)

alerts = fetch_monitoring_alerts("https://nexus.example")
summary = fetch_monitoring_summary("https://nexus.example")
analysis = analyze_monitoring_alert(
    "https://nexus.example",
    alerts[0].alert_id,
    question="What evidence should the desk verify?",
)
```

The SDK calls the same backend API and never accepts a DeepSeek key.

## Operator Validation

The following checks are non-secret. Do not place an API key in a command line.

```powershell
docker compose --env-file .env -f compose.yaml --profile monitoring ps
docker compose --env-file .env -f compose.yaml logs --tail 100 monitoring-worker
```

Use the Data Sources credential form for key entry and connection testing. Use
the Alert Center for a real completion test. Confirm the provider status is
`success`, the answer is visible, and no credential appears in API responses or
logs.

Automated tests replace the provider callable and never contact DeepSeek.
