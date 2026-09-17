# W8-01 — Product Error Taxonomy

Status: **delivered (Wave 8, taxonomy and presentation layers)**. Authority:
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 6,
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rule 37, and
[04_PRODUCT_EXPERIENCE_ARCHITECTURE.md](04_PRODUCT_EXPERIENCE_ARCHITECTURE.md) section 7.

## 1. What the wave requires

A failure must answer four questions in one consistent place — what happened, what it affects, the
likely cause, how to recover — through a stable code, with a correlation id, and with operator detail
only on operator surfaces. Today the repository returns twenty ad-hoc codes and the client renders
whatever string arrives.

## 2. Delivered

| Layer | Module | Content |
|---|---|---|
| Catalogue | `src/eurogas_nexus/domain/operations/error_taxonomy.py` | Ten families (`AUTH`, `ENTITLEMENT`, `VALIDATION`, `DATA`, `CALCULATION`, `DEPENDENCY`, `CONFIGURATION`, `JOB`, `AGENT`, `SYSTEM`), severity, recoverability, translation keys per code, family inference for uncatalogued codes, and `error_payload()` |
| Bridge | same module | `family_for_operational_category()` maps the pre-existing infrastructure taxonomy (`operations/errors.py`) onto the product families, so the two vocabularies do not compete |
| API envelope | `src/eurogas_nexus/api/error_handlers.py`, wired in `api/app.py` | Every `HTTPException` keeps the `detail` the endpoint raised — a string stays a string, a dict keeps every key — and gains `error`, `family`, `severity`, `recoverability`, `message_key`, `action_key` and `correlation_id` (the same value as the `X-Request-Id` header) alongside it, plus `operator_detail` only for an operator identity |
| Client presentation | `clients/web/src/app/experience/errorPresentation.ts` | `describeApiError()` turns a payload into the four questions; `isRetryable()` / `requiresUserAction()` let a surface decide whether to offer a retry |
| Vocabulary | `clients/web/src/i18n/{en,zh-CN}.json` | `errors.<code>.message`, `errors.<code>.action`, `errors.family.<FAMILY>.{title,impact,cause,action}` and the specific cause keys the presentation can emit |

Coverage: the catalogue explains every code the repository already returns
(`unauthenticated`, `entitlement_denied`, `permission_not_declared`, `runtime_db_unavailable`,
`dataset_spec_invalid`, `public_api_token_not_configured`, …) plus the failure modes Architecture V2
names (`DATA_STALE`, `DATA_MISSING`, `PORTFOLIO_INCOMPLETE`, `SNAPSHOT_EXPIRED`, `ROUTE_INFEASIBLE`,
`OPTIMIZATION_INFEASIBLE`, `PROVIDER_UNAVAILABLE`, `AGENT_BUDGET_EXCEEDED`,
`commercial_access_not_granted`, `JOB_FAILED`, …). The API raises several dozen more specific codes;
those keep their own identifier and gain a family inferred from the code shape, with family-level
translation keys, so a client always has text to render instead of a missing-key placeholder.

## 3. Rules

1. **A code is never a raw exception string.** An uncatalogued code still produces a valid payload
   through the `SYSTEM` fallback, and the client explains it generically *with* the correlation id
   rather than showing nothing.
2. **Operator detail never reaches a business user.** `error_payload(..., detail=…)` drops the detail
   unless the caller declares an operator surface, and informational severities never carry one.
3. **Severity is not alarm.** A stale-but-usable slice is a `warning`; only a failed request or an
   internal fault is an `error`/`critical`.
4. **Messages are translation keys.** The backend returns `message_key`/`action_key`; EN and zh-CN
   stay in step because the client renders keys, not prose (a safe backend message may override the
   text while keeping the keys).
5. **Unknown input fails closed.** An unrecognised family, severity or recoverability degrades to the
   safe default instead of claiming a lower severity.

## 4. The unhandled-failure envelope (delivered)

`HTTPException` was enveloped from the start; an unexpected exception still answered with the
framework's bare 500, which a V2 client cannot explain and an operator cannot match to a log line.
That path is now enveloped as well, and the bargain is explicit:

- the client gets the `internal` code (family SYSTEM, severity critical), a recoverability, a message
  and action key, and an **always-present** correlation id echoed on `X-Request-Id` - even when the
  request never reached the middleware that stamps one;
- FastAPI's own user-facing text stays in `detail`, so a client that reads `detail` is unaffected;
- the exception's **own message never travels**: it can carry commercial values (a row, a price, a
  query fragment), so a business identity reads an explainable envelope and nothing else;
- an operator identity additionally receives `operator_detail` with the fault's **class name**, which
  is what makes it matchable to the server log;
- the failure is not hidden: Starlette re-raises after the response is sent, so logging and monitoring
  keep seeing the real traceback.

## 5. Deferred (explicit)

- **Unified Job model.** `JOB_FAILED`/`JOB_CANCELLED` are catalogued, but a shared job lifecycle
  (`QUEUED`…`EXPIRED` with progress, retries, cancellation) is not implemented. That is the other
  half of Wave 8 and needs its own schema decision.
- Business-health vs technical-health separation and the diagnostics bundle remain Wave 8/9 work.

## 6. Verification

- `tests/unit/test_error_taxonomy.py` — catalogue completeness and typing, coverage of the codes the
  API already returns, the V2-named failure modes, family inference for uncatalogued codes,
  fail-closed unknown handling, payload shape with correlation id, operator-detail suppression,
  safe-message override, the infrastructure bridge, and stable grouping.
- `tests/api/test_error_envelope.py` — a declared code keeps its `detail` and gains the taxonomy; the
  commercial refusal is an ENTITLEMENT failure; a string detail stays a string; an uncatalogued
  endpoint code is still classified; a missing API token is a CONFIGURATION failure; and
  `operator_detail` appears only for an operator identity. The correlation id equals the
  `X-Request-Id` header.
- `tests/api/test_unhandled_error_envelope.py` — an unexpected failure answers with the SYSTEM
  envelope, an always-present correlation id echoed on the header, and FastAPI's own `detail` text; the
  exception's message never reaches the client (no value, no class name, no traceback) and no
  `operator_detail` is present for a business identity; the operator path exposes the class name only;
  and a declared `HTTPException` code is untouched by the new handler.
- `clients/web/tests/errorPresentation.test.ts` — the four questions for a catalogued failure, the
  administration-versus-commercial refusal, retry/user-action classification, fail-closed behaviour
  for unknown, missing and malformed payloads, message trimming, and bilingual key coverage.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` and
  `node --test "tests/*.test.ts"` in `clients/web` (both green).
