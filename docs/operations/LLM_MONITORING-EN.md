# DeepSeek Live Monitoring and Interaction

## Purpose

Eurogas Nexus uses DeepSeek as a governed analysis layer over deterministic,
PostgreSQL-backed monitoring events. DeepSeek does not discover spreads, decide
capacity feasibility, calculate route cost, or execute business actions. Those
results remain owned by the market, route, strategy, ingestion, and risk engines.

The current provider configuration is fixed to **DeepSeek V4 Flash** with API model
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
for Server installation. Losing this encryption key makes existing
credential rows unusable; rotate provider keys after restoring the runtime.

## Worker Service Identity (Owner Decision D7)

Alert enrichment runs under a named service identity, not the deployment token
and not an unnamed process. Before any credential is loaded or provider call is
made, the worker re-reads the identity named in `EUROGAS_NEXUS_WORKER_PRINCIPAL`
from the runtime database and requires it to be an **ACTIVE SERVICE principal**
(never a human `USER` identity) that holds `analysis.query` (an `ANALYST` role
grants it). The identity is re-read on every enrichment attempt, so deactivating,
disabling or downgrading it takes effect without restarting the worker.

When the identity is missing or unusable, the worker reports `enrichment:
refused` on its start-up line and `llm_enrichment_refused` with a declared reason
on each scan (`service_principal_not_configured`, `service_principal_unknown`,
`service_principal_inactive`, `service_principal_human_identity`,
`service_authority_not_granted`), and records the refusal in the audit trail
(`governance.ai_authority` / `monitoring.enrichment.refused`) without naming a
credential. Alerts stay unanalysed (`pending`) instead of spending a provider
call with nobody's authority behind it; scanning and persistence continue. A
call that is allowed is attributed to the same persisted principal
(`governance.ai_authority` / `monitoring.enrichment.provider_call`).

Set `EUROGAS_NEXUS_WORKER_PRINCIPAL` in the `monitoring-worker` environment to
the provisioned identity name. The shipped `deploy/runtime/compose.yaml` does
not pass this variable to the worker container yet, so a compose deployment
refuses enrichment until that deployment wiring exists; that wiring and a live
revocation exercise are still open deployment work.

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

`POST /api/monitoring/alerts/{alert_id}/acknowledge` is a governed write: it
requires the `GOVERNED` permission (ANALYST floor) and stays inside the
commercial-data boundary, so a platform-administration-only identity cannot
call it. The acknowledger is the authenticated principal resolved from the
request identity - never a request-body field. The state transition and its
audit record are written in one transaction; the record names the principal,
the resource (`monitoring_alert:<alert_id>`) and the request correlation id,
and is readable through the existing `GET /api/audit` surface
(`audit.read`/ADMIN). A repeat acknowledgement preserves the original
acknowledger and timestamp, and a resolved alert is not reopened or
acknowledged.

No client accesses PostgreSQL or DeepSeek directly.

Python SDK users import from `eurogas_nexus_sdk.monitoring`:

```python
from eurogas_nexus_sdk.monitoring import (
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

## Choosing the model per installation

The adapter speaks the OpenAI-compatible chat-completions API, so the model is
installation configuration rather than code:

| Variable | Default | Example |
|---|---|---|
| `EUROGAS_NEXUS_LLM_BASE_URL` | `https://api.deepseek.com` | `https://<resource>.openai.azure.com/openai/v1`, `https://api.mistral.ai/v1`, `http://10.0.4.20:8000/v1` (vLLM on-premises) |
| `EUROGAS_NEXUS_LLM_MODEL` | `deepseek-v4-flash` | `mistral-large-latest`, `qwen2.5-72b-instruct` |
| `EUROGAS_NEXUS_LLM_PROVIDER_NAME` | `DEEPSEEK` | `AZURE_OPENAI`, `MISTRAL`, `ONPREM` |

HTTPS is required; plain HTTP is accepted only for a model on a private network. The
provider name is recorded with every answer and in the audit trail. Pick the model by
installation (see `docs/architecture/GLOBAL_DEPLOYMENT.md`): an EU-hosted or on-premises
model for the primary installation if prompts must stay in Europe, an in-country model
for the China installation. `EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED` still has to allow
external calls, and payloads never include licensed raw prices.


## Provider payloads and the evaluation set (AI-04)

Every model text is shown only if it passes the checks in `application/ai_style.py`
(`note_verdict` for a desk note, `answer_verdict` for an answer, both summaries for the
alert enrichment) and the ontology grounding in `application/grounding.py`. Otherwise the
rule text stands (Why, brief), the deterministic answer stands (analysis query), the
answer is withheld with `model_answer_refused:<check>` (alert analysis), or the alert keeps
no summary with `llm_status = checks_refused` (enrichment). The checks refuse: invalid
format, over length, a foreign citation, a number not in the evidence, advice to trade or
nominate, a simulated price that reads as a market price, a hub, unit, number-unit pair,
direction (per figure: the evidence's own clause or sign), superlative, source or name
the evidence does not contain. Chinese unit spellings are read as their codes.

### What each use sends

| Use | Route / caller | User payload fields | Not sent (removed 2026-11-15) |
|---|---|---|---|
| "Why?" | `POST /api/analysis/explain` | `object` (title), `facts` (the rule lines), `sources` as `S1`..`Sn`, `simulated_inputs` | the raw evidence row (ids, provider references, unrounded values); real source ids |
| Desk brief lead | `POST /api/analysis/brief` | `brief` (kind), `sections` (heading -> lines), `sources` as `S1`..`Sn`, `simulated_inputs` | real source ids (counterparty, snapshot, REMIT ids) |
| Report section wording | `POST /api/reports/market` | `section` (title), `lines` (the rule headline and facts), `sources` as `S1`..`Sn`, `simulated_inputs`, `forecast` (`REPORT_SECTION_FIELDS`) | tables, figures not in the lines, book ids, source systems, provider references; Our book sections are never sent |
| Report plan | `POST /api/reports/plan` | `question`, `sections` (catalogue key and one-line description; no book section for a shareable audience), `hubs` and `countries` (codes), `audience` (`REPORT_PLAN_FIELDS`) | any figure or row; the plan is used only if it validates against the catalogue and names no hub the question did not |
| Alert answer | `POST /api/monitoring/alerts/{id}/analysis` | `question`; `alert`: `category`, `alert_type`, `severity`, `status`, `title`, `message` (reply language only), `event_time_utc`, `occurrence_count`, `evidence` (identifier fields removed), `simulated` | alert id, fingerprint, entity ids, earlier model summaries, `llm_*` fields, warnings, source refs, the other language |
| Alert enrichment | monitoring worker | `category`, `type`, `severity`, `title_en`, `message_en`, `evidence` (identifier fields removed), `simulated` | source references, warnings (they carried earlier provider errors), identifier fields in the evidence |
| Analysis query | `POST /api/analysis/query` with `invoke_provider` | `question`, `task`, `snapshot` with every identifier field removed at any depth (`*_id`, `*_ids`, `*_eic`, `fingerprint`, `*reference*`, `source_refs`); contract prices only on opt-in | snapshot id, contract ids, run ids, provider references |

The allowlist is enforced by `tests/security/test_ai_payload_allowlist.py` (provider
stubbed, outgoing messages captured); the field lists live in
`application/ai_payloads.py`. Entitlement still decides first whether any call is made.

### Market reports (2026-11-16)

The model may reword a market report section's rule commentary (`application/reports/rewrite.py`,
checked by `note_verdict` like a desk note; refused text leaves the rule text, and each verdict
is stored in the report's `model_use`) and may propose a report plan from a question
(`application/reports/plan.py`; the proposal must validate against the catalogue and may name
only hubs the question names, else the keyword rules propose). The evaluation set has a `report`
use (5 evidence payloads, 15 cases, good and adversarial, English and Chinese) and
`tests/evals/report_plan_cases.json` (12 plan cases, incl. a shareable question asking for the
book, out-of-scope questions, ETF not becoming TTF, SQL from the model). Live run on 2026-11-16
(DeepSeek V4 Flash, public store, 10 section rewrites): 10 of 10 passed the checks; both asked
questions got a valid model plan.

### Call budgets

`ai_style.NOTE_CALL`, `ANSWER_CALL`, `ENRICHMENT_CALL`. DeepSeek V4 Flash reasons before it
writes and counts those tokens in `max_tokens`: the earlier 300-token budget for notes
returned an empty reply on most calls, so the rule text always stood. Notes now allow 3000
tokens, answers and enrichment 2000; the reply length is held by the checks.

### The evaluation set

`tests/evals/ai_note_cases.json`: recorded demo and public-shaped evidence for every use
(Why, brief, alert answer in English and Chinese, enrichment), and candidate outputs with
the verdict each must get and why. `tests/evals/test_ai_note_evals.py` runs them through the
product's own payload builders and checks in CI, without a provider, and prints the
correct-verdict rate per category (`pytest -s`).

On demand, with a provider:

    python scripts/ai/run_note_eval.py --repeat 5 --json report.json

It sends only the recorded set, refuses in trial or release profiles, refuses when any
evidence is not marked demo or public, and refuses when a configured runtime database holds
any trading book not named `demo-`. It reports the share of model outputs that pass, the
refusal reasons, the median latency and how often the rule text stood.

Run on 2026-11-15 (DeepSeek V4 Flash, 9 evidence payloads x 5): 40 of 44 model outputs
passed (90.9 %), the rule text stood in 11.1 % of calls (including one provider transport
error), median latency 3.5 s. Refusals: one empty reply (brief), one Chinese answer that
used 提名 (nomination) as a noun (conservatively refused as advice), one "over its limit"
where the evidence says "against", one hyphenated name since fixed.
