# Python SDK troubleshooting

What goes wrong when calling Eurogas Nexus from Python, how to tell which problem you have,
and what to do about it.

## Read the error

The SDK lets four kinds of exception through:

| Exception | Meaning | First thing to check |
|---|---|---|
| `eurogas_nexus_sdk.NexusAPIError` (an `httpx.HTTPStatusError`) | The server answered with a 4xx or 5xx status | `error.code` and `error.message` |
| `httpx.TransportError` (`ConnectError`, `ConnectTimeout`, `ReadTimeout`, ...) | No usable answer: server down, wrong address, network or timeout | The address and whether the server is running |
| `pydantic.ValidationError` | The server answered, but not in the shape the SDK model expects | Server and SDK versions; whether the server has a database |
| `eurogas_nexus_sdk.SdkProtocolError` | The answer was not a Eurogas Nexus `{data, meta}` envelope | The address points at the API server, not at a proxy page or the web client |

`NexusAPIError` carries what the server said, so the body never needs parsing:

```python
from eurogas_nexus_sdk import NexusAPIError
from eurogas_nexus_sdk.reference_network import fetch_node

try:
    fetch_node("http://127.0.0.1:8000", "NO-SUCH-NODE")
except NexusAPIError as error:
    print(error.status_code)      # 404
    print(error.code)             # the endpoint's own code if it gave one, else error.error
    print(error.error)            # not_found: the catalogue code, the same on every endpoint
    print(error.family)           # VALIDATION
    print(error.recoverability)   # retry | after_user_action | permanent | unknown
    print(error.correlation_id)   # also the X-Request-Id header; quote it to an administrator
    print(error.message)          # what to do, in words; for 422 one entry per field
    print(error.detail)           # the endpoint's detail exactly as sent
```

`str(error)` reads like `404 not_found: ... (correlation id ...)`. Branch on `code` or `error`,
show `message` to people. `error.response` is still the `httpx.Response`, so code written
for `httpx.HTTPStatusError` keeps working.

## Decide whether to retry

The SDK never retries. Use `recoverability`:

| `recoverability` | Retry? |
|---|---|
| `retry` | Yes, with back-off, for reads |
| `after_user_action` | No. Fix the input, the credential or the entitlement first |
| `permanent` | No |
| `unknown` | No; report it with the correlation id |

Retry a `TransportError` on a read, too. Never retry a call that records something
(`record_review_decision`, `acknowledge_monitoring_alert`, `functional.submit_run`): it could be recorded twice. `submit_run` and
`replay_run` take an `idempotency_key`; reuse the same key when you resend.
[`examples/sdk/10_errors_and_retries.py`](../../examples/sdk/10_errors_and_retries.py) has a
`with_retries` helper.

## Connection and address problems

| Symptom | Cause | Fix |
|---|---|---|
| `ConnectError: [Errno 111] Connection refused` | Nothing listens at that address and port | Start the server, or correct the port |
| `404` on every call, URL contains `/api/api/` | `base_url` already ends in `/api` (the desktop client's setting uses that form) | Pass the origin only: `https://nexus.example.com` |
| `404` from some functions only, URL contains `//api/` | `base_url` ends in `/`; some modules do not strip it | Remove the trailing slash |
| `ReadTimeout` | The call took longer than its fixed timeout (10 to 30 seconds depending on the function) | Narrow the request where the function has filters; the timeout itself cannot be changed except for `fetch_health`, `stream_events` and `calculate_nwe_balance_scenario` |
| TLS or certificate errors against an internal server | Your firm's CA is not trusted by Python | `httpx` honours the `SSL_CERT_FILE` and `SSL_CERT_DIR` environment variables and the `HTTPS_PROXY` family. Not tested while this guide was written |
| `SdkProtocolError: Backend response is missing data/meta envelope fields.` | The address answers, but it is not the Eurogas Nexus API (for example a sign-in proxy page) | Use the API server's address; ask IT for it |

## Authentication and access

| Status and code | Cause | Fix |
|---|---|---|
| `401 public_api_token_missing` | No deployment token in the environment of the Python process | `export EUROGAS_NEXUS_PUBLIC_API_TOKEN=...` in that shell, or in the notebook's kernel environment |
| `403 public_api_token_invalid` | Wrong deployment token, or an identity key placed in the token variable | Identity keys go in `EUROGAS_NEXUS_IDENTITY_BEARER` |
| `503 public_api_token_not_configured` | The server itself has no deployment token | The administrator configures it |
| `401 identity_bearer_missing` | The identity key is truncated or not `nexus_<key_id>_<secret>` | Copy the whole key |
| `403 identity_key_invalid`, `identity_key_revoked`, `identity_key_expired` | The key is unknown, revoked or expired | Ask for a new key |
| `403 identity_role_forbidden`, `permission_denied` | Your role does not cover the action | Ask for the role |
| `403 commercial_access_not_granted`, `entitlement_denied`, `export_denied` | Your data scopes do not cover this data family | Ask for the data scope; a key's scopes are cut to its owner's |
| `401 operator_principal_missing` | Operator write route called with the deployment token alone | Use an operator's identity key, or set `EUROGAS_NEXUS_PRINCIPAL` |

Details: [Authentication](AUTHENTICATION.md).

## Data problems

| Symptom | Cause | Fix |
|---|---|---|
| Empty lists everywhere, `meta.warnings` mentions the runtime DB | The server runs without a database | The administrator sets `RUNTIME_STORE_DATABASE_URL` |
| `pydantic.ValidationError` from `fetch_desk_today` with `Field required` | Same: a server without a database returns an empty Today read | Same |
| `503 runtime_db_unavailable` (`recoverability: retry`) | The database did not answer | Retry later; if it persists, report the correlation id |
| A list is empty but no error | No data loaded for that source, or your scopes hide it | Check `sources.fetch_sources_result` for the source's `operational_status` (`no_records`, `needs_credential`, `active`) |
| Values are `None` | The value is missing at the source | Missing is not zero; do not fill it with 0 |
| Rows say `simulated: True` or the source is `DEMO_Sim` | Demo or simulated data | Do not use for decisions; a production server has none |
| `422 fx_rate_unavailable` from `convert_gas_price_result` with `to_unit` | No stored FX fix for that currency pair (the server reports `recoverability: unknown`) | Pass `gbp_per_eur` / `usd_per_eur`, or name `fx_source` and `fx_date` |
| `route_cost.calculate_route_cost` returns `status` `BLOCKED` with `missing_inputs` `['ROUTE_TARIFF_LEGS_REQUIRED']` | No `tariff_legs` given | Pass the legs of a route candidate; see [Examples](EXAMPLES.md#cost-of-a-route-between-hubs) |
| `SdkPageLimitError` from `market.fetch_market_observations` | The range needs more pages than `max_pages` (the read is paged, 1,000 rows a page) | Pass a narrower `from_utc`/`to_utc` or a `product`, or raise `max_pages` |

## Version mismatches

| Symptom | Cause | Fix |
|---|---|---|
| `ValidationError` on a field you did not ask for | SDK and server come from different releases, or the server returns a value the SDK model does not allow | Install the SDK from the server's release (`fetch_health(...).version`) |

## Error codes

The server's catalogue of stable codes, with the recoverability it reports. Endpoints may
also return more specific codes; those still carry `family` and `recoverability`.

| Code | Family | Recoverability | Meaning |
|---|---|---|---|
| `public_api_token_missing` | AUTH | after_user_action | The deployment API token is missing |
| `public_api_token_invalid` | AUTH | after_user_action | The deployment API token was rejected |
| `public_api_token_not_configured` | CONFIGURATION | unknown | The server has no deployment token |
| `operator_principal_missing` | AUTH | after_user_action | No operator principal named |
| `identity_role_forbidden` | AUTH | permanent | The role does not cover the action |
| `permission_denied` | AUTH | permanent | The identity lacks the capability |
| `commercial_access_not_granted` | ENTITLEMENT | after_user_action | Administration alone grants no commercial data |
| `entitlement_denied` | ENTITLEMENT | permanent | The data licence does not cover this caller |
| `entitlement_unavailable` | ENTITLEMENT | retry | Entitlement could not be determined |
| `export_denied` | ENTITLEMENT | permanent | Export is restricted for this dataset |
| `validation_failed` | VALIDATION | after_user_action | The input did not pass validation |
| `not_found` | VALIDATION | permanent | The record does not exist |
| `conflict` | VALIDATION | after_user_action | The request conflicts with the current state |
| `rate_limited` | DEPENDENCY | retry | Too many requests in a short window |
| `service_unavailable` | DEPENDENCY | retry | A required service is unavailable |
| `runtime_db_unavailable` | DEPENDENCY | retry | The database could not be reached |
| `runtime_db_required` | CONFIGURATION | after_user_action | The action needs the database |
| `PROVIDER_UNAVAILABLE` | DEPENDENCY | retry | A data provider did not answer |
| `DATA_STALE` | DATA | retry | The newest value is older than expected |
| `DATA_MISSING` | DATA | unknown | Required data is missing |
| `SNAPSHOT_EXPIRED` | DATA | after_user_action | The result was computed on an outdated snapshot |
| `ROUTE_INFEASIBLE` | CALCULATION | after_user_action | No feasible route for the constraints |
| `OPTIMIZATION_INFEASIBLE` | CALCULATION | after_user_action | No allocation satisfies the constraints |
| `JOB_FAILED` | JOB | retry | A background job did not complete |
| `internal` | SYSTEM | unknown | Unexpected server error; quote the correlation id |

The full list (55 codes) is `ERROR_CATALOGUE` in
`src/eurogas_nexus/domain/operations/error_taxonomy.py`; the English and Chinese texts are in
`clients/web/src/i18n/en.json` and `zh.json` under `errors.<code>`.

## Report a problem

Send your support contact: the `correlation_id`, the time, the function you called, the SDK
version (`importlib.metadata.version("eurogas-nexus")`) and the server version
(`fetch_health(base_url).version`). Do not send tokens, keys or response bodies with
licensed data. See [Support and updates](../guides/SUPPORT_AND_UPDATES.md).
