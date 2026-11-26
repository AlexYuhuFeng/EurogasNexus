# Eurogas Nexus Python SDK

`eurogas_nexus_sdk` is the Python client for the Eurogas Nexus `/api`. It reads prices,
fundamentals, positions and research results from a Eurogas Nexus server and returns them as
typed models, with the server's provenance and warnings attached.

The SDK is decision support only. It reads data and runs server-side calculations; it never
places orders, executes trades, sends nominations or settles. Every response says so in its
metadata (`research_only`, `human_review_required`).

| You want to | Read |
|---|---|
| Get a first result in five minutes, on a local demo server | [Quickstart](../../docs/sdk/QUICKSTART.md) |
| Connect to your firm's server | [Authentication](../../docs/sdk/AUTHENTICATION.md) |
| Do a specific task (prices, storage, spreads, route cost, limits) | [Examples](../../docs/sdk/EXAMPLES.md) |
| Look up a function, its parameters and the endpoint it calls | [Reference](../../docs/sdk/REFERENCE.md) |
| Fix an error | [Troubleshooting](../../docs/sdk/TROUBLESHOOTING.md) |

## Install

The SDK ships inside the `eurogas-nexus` distribution; there is no separate SDK package.
Install the wheel delivered with your release, in its own virtual environment, with
Python 3.11 or later:

```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install eurogas_nexus-1.0.0b1-py3-none-any.whl
```

From a source checkout, `python -m pip install -e .` at the repository root does the same.

The wheel also installs the server's dependencies (FastAPI, SQLAlchemy, Alembic, uvicorn and
others) because server and SDK share one distribution. The SDK itself uses only `httpx` and
`pydantic`.

Use the SDK from the same release as the server. The SDK has no version of its own: check it
with `importlib.metadata.version("eurogas-nexus")` and compare it with the `version` that
`fetch_health` returns.

## Configure

Every function takes the server address as its first argument, `base_url`. Pass the origin
only, without `/api` and without a trailing slash: `https://nexus.example.com` or
`http://127.0.0.1:8000`. The SDK adds `/api/...` itself.

Credentials are read from environment variables on every call. There is no client object
and no per-call credential argument.

| Variable | Needed | Sent as |
|---|---|---|
| `EUROGAS_NEXUS_PUBLIC_API_TOKEN` | Always, except for `fetch_health` | `Authorization: Bearer <token>` |
| `EUROGAS_NEXUS_IDENTITY_BEARER` | When your administrator issued you a personal or service key (`nexus_...`) | `X-Eurogas-Identity` |
| `EUROGAS_NEXUS_PRINCIPAL` | Only for operator routes called with the deployment token alone | `X-Eurogas-Principal` |

```bash
export EUROGAS_NEXUS_PUBLIC_API_TOKEN='<deployment token from your administrator>'
export EUROGAS_NEXUS_IDENTITY_BEARER='<your nexus_... key>'
```

With the deployment token alone the server treats you as a shared compatibility caller; with
an identity key it applies your own role and data scopes. The SDK cannot send an OIDC access
token. See [Authentication](../../docs/sdk/AUTHENTICATION.md) for the details and for what
each refusal means.

## First call

```python
from eurogas_nexus_sdk import fetch_health
from eurogas_nexus_sdk.desk import fetch_desk_today_result

BASE_URL = "http://127.0.0.1:8000"

print(fetch_health(BASE_URL))                 # no credential needed

result = fetch_desk_today_result(BASE_URL)    # needs EUROGAS_NEXUS_PUBLIC_API_TOKEN
today = result.data
print(today.gas_day, today.front_month, today.focus_hubs)
print(result.meta.source_references, result.meta.warnings)
```

`fetch_health` tells you the server is up and which version it runs. It says nothing about
whether data has been loaded.

## How the SDK is organised

- One module per area: `market`, `physical`, `storage`, `lng`, `desk`, `portfolio`,
  `research`, `route_cost`, `optimization`, `strategy_lab`, `reference_network` and others.
  The [reference](../../docs/sdk/REFERENCE.md) lists all 33 modules and 150 functions.
- Functions, not a client class. Import the function from its module and pass `base_url`.
- Read functions are named `fetch_*` or `list_*`; server-side calculations are named
  `compute_*`, `calculate_*`, `analyse_*` or `optimize_*`. A few functions record something
  on the server (`record_review_decision`, `acknowledge_monitoring_alert`, the
  `strategy_registry` create and update functions); the reference marks them as `POST`,
  `PUT` or `PATCH`.
- Many read functions come in two forms. `fetch_market_quotes_result()` returns an
  `SdkResult` with `.data` and `.meta`; `fetch_market_quotes()` returns only the data. Use the
  `_result` form whenever provenance matters: `meta.source_references`, `meta.warnings`,
  `meta.research_only` and `meta.human_review_required` come from the server.
- Results are pydantic models in the server's own units. Nothing is converted on the client.
  A missing value is `None`, never zero. Rows carry `simulated` or a `metadata_json` flag
  when they come from demo or simulated sources.
- Some calculation functions take keyword arguments that are passed to the server as the
  JSON body (`calculate_route_cost(base_url, **scenario)`). Their accepted fields are the
  request schema of the matching endpoint; see the reference for the endpoint name.

## Common tasks

Each task links to a runnable script in [`examples/sdk`](../../examples/sdk).

| Task | Role | Functions |
|---|---|---|
| [Today: prices, book and P&L change in desk units](../../docs/sdk/EXAMPLES.md#todays-prices-and-book) | Trader, risk | `desk.fetch_desk_today_result` |
| [Bid/ask board for a hub](../../docs/sdk/EXAMPLES.md#bidask-board-for-a-hub) | Trader | `market.fetch_market_quotes_result` |
| [Convert a price between EUR/MWh, p/th and USD/MMBtu](../../docs/sdk/EXAMPLES.md#convert-a-price) | Trader, analyst | `market.convert_gas_price_result` |
| [Storage against the EU target](../../docs/sdk/EXAMPLES.md#storage-against-the-eu-target) | Analyst | `storage.fetch_storage_target_trajectory`, `storage.fetch_storage_sites` |
| [Backtest a spread rule](../../docs/sdk/EXAMPLES.md#backtest-a-spread-rule) | Analyst, quant | `research.list_spread_series`, `research.analyse_spread` |
| [Cost of a route between hubs](../../docs/sdk/EXAMPLES.md#cost-of-a-route-between-hubs) | Trader, analyst | `route_cost.fetch_route_candidates`, `route_cost.calculate_route_cost` |
| [Limits and outages that touch the book](../../docs/sdk/EXAMPLES.md#limits-and-outages) | Risk | `desk.fetch_desk_today_result`, `physical.fetch_outages_result` |
| [Keep provenance and warnings with the numbers](../../docs/sdk/EXAMPLES.md#keep-provenance-and-warnings) | Everyone | `*_result` functions, `sources.fetch_sources_result` |

## Errors, timeouts and retries

The SDK does not wrap errors in its own exception classes. Expect four kinds:

| Exception | When |
|---|---|
| `eurogas_nexus_sdk.NexusAPIError` (an `httpx.HTTPStatusError`) | The server answered 4xx or 5xx. It carries the stable `code`, a `message`, a `recoverability` hint and the `correlation_id`. |
| `httpx.TransportError` (`ConnectError`, `ReadTimeout`, ...) | The server could not be reached or did not answer in time. |
| `pydantic.ValidationError` | The server's answer did not match the SDK model, for example an empty read from a server with no database. |
| `eurogas_nexus_sdk.SdkProtocolError` | The answer was not a Eurogas Nexus `{data, meta}` envelope. |

```python
from eurogas_nexus_sdk import NexusAPIError
from eurogas_nexus_sdk.desk import fetch_desk_today

try:
    today = fetch_desk_today("http://127.0.0.1:8000")
except NexusAPIError as error:
    print(error.status_code, error.code, error.message)
    print("quote this to an administrator:", error.correlation_id)
```

`NexusAPIError` is a subclass of `httpx.HTTPStatusError`, so code that already catches that
keeps working; `error.response` is still there.

Timeouts are fixed per function, between 10 and 30 seconds; only `fetch_health`,
`streaming.stream_events` and `fundamentals.calculate_nwe_balance_scenario` accept a
timeout argument. The SDK never retries. Retry reads yourself on a `TransportError` or on an
answer whose `recoverability` is `retry`, and never retry a call that records something.
[Example 10](../../examples/sdk/10_errors_and_retries.py) has a small wrapper, and
[Troubleshooting](../../docs/sdk/TROUBLESHOOTING.md) lists the error codes.

List reads take an optional `limit` where the endpoint supports one. Market observations and
FX are paged by range (`meta.continuation`, 1,000 rows a page): `market.fetch_market_observations`
takes `from_utc`/`to_utc` and `product`, reads every page of the range, and raises
`SdkPageLimitError` rather than return part of it.

## Versions and compatibility

- The SDK version is the `eurogas-nexus` package version (`1.0.0b1` for the 1.0.0 beta; the
  server reports it as `1.0.0-beta`). Releases follow
  [Semantic Versioning](https://semver.org/); see [Release channels](../../docs/release/RELEASE_CHANNELS.md).
- Use the SDK from the same release as the server. Mixed versions are not tested.
- Changes to `/api` are governed by the
  [API contract evolution policy](../../docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md):
  new endpoints and optional fields are added; a removal or rename is deprecated first, keeps
  working for at least one release, and is announced in `meta.warnings` on the affected
  response, in the policy's deprecation table and in the [Changelog](../../CHANGELOG.md).
  Log `meta.warnings` in automated jobs so you see a deprecation before it bites.
- Most SDK models ignore response fields they do not know. The strict ones
  (`native_physical`, `weather_forecasts`, `weather_degree_days`, `capacity_billing`,
  `lng_economics_only`) refuse them, which is one more reason to keep SDK and server on the
  same release.

## Rules for scripts and notebooks

- Keep tokens and keys in the environment or a secret store, never in notebooks, shared
  examples or logs.
- Keep the server version, the SDK version, the request and the returned metadata with any
  result you share.
- The SDK talks only to the server's `/api`. It never reads the database, files or vendor
  APIs directly.

## Contributing to the SDK

Source: `packages/python-sdk/src/eurogas_nexus_sdk`. Tests: `tests/sdk`, the parity tests in
`tests/contract/test_sdk_*.py`, and the installed-wheel acceptance in
`.github/workflows/sdk-acceptance.yml`. After changing a public function, regenerate the
reference with `python scripts/docs/generate_sdk_reference.py --output docs/sdk/REFERENCE.md`.
Design rules: [SDK and CLI contract](../../docs/clients/SDK_CLI_CONTRACT.md).
