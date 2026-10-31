# Platform administrator and data operator guide

**You land on Administration → Access (admin) or System → Sources (data operator).**

## Install and run

Deployment roles, prerequisites and the Windows deployment tool:
[DEPLOYMENT_ROLES-EN.md](../deployment/DEPLOYMENT_ROLES-EN.md). Global topology:
[GLOBAL_DEPLOYMENT.md](../architecture/GLOBAL_DEPLOYMENT.md). Configuration is validated
at start-up (`python scripts/ops/check_config.py --strict`).

## People and access

- Create users or let SSO provision them; assign **roles** and **data scopes** only against
  a request approved by the desk head. You cannot change your own grants.
- Set job functions and office (Access → Job profile). They choose landing pages; they
  grant nothing.
- Organisation defaults (language, theme, landing views, profit colour, languages offered):
  Settings → Organisation defaults.

## Data sources

| Source | How it runs | Guide |
|---|---|---|
| ENTSOG, GIE, ECB FX | Data-ops scheduler (`scripts/ops/run_dataops_scheduler.py`) | Source Center |
| SONIA, €STR, SOFR | Data-ops scheduler, once a business day after each publication | [INTEREST_RATES.md](../operations/INTEREST_RATES.md) |
| ENTSO-E power | Data-ops scheduler, hourly; enable in Source Center once `ENTSOE_SECURITY_TOKEN` is set | [POWER_DATA.md](../operations/POWER_DATA.md) |
| ECMWF temperature | `scripts/ops/ingest_ecmwf_forecasts.py` | [ECMWF_FORECAST_OPERATIONS.md](../data/ECMWF_FORECAST_OPERATIONS.md) |
| National Gas demand | `scripts/ops/ingest_national_gas_rest.py` | [NATIONAL_GAS_REST_OPERATIONS.md](../data/NATIONAL_GAS_REST_OPERATIONS.md) |
| REMIT outages (UMMs) | `scripts/ops/import_remit_umm.py` | [REMIT_OUTAGES.md](../operations/REMIT_OUTAGES.md) |
| Licensed settlements (EUA, UKA, API2, power, gas, Henry Hub, AECO) | `scripts/ops/import_settlements.py` | [MARKET_DATA_SOURCING.md](../operations/MARKET_DATA_SOURCING.md) |
| Henry Hub spot (EIA) | Data-ops scheduler, daily; set `EIA_API_KEY` | [MARKET_DATA_SOURCING.md](../operations/MARKET_DATA_SOURCING.md) |
| Licensed quotes, FX fixings | `scripts/ops/import_market_quotes.py`, `import_fx_fixings.py` | [LIVE_PRICE_SOURCES.md](../operations/LIVE_PRICE_SOURCES.md), [FX_FIXINGS.md](../operations/FX_FIXINGS.md) |
| Weather-demand model | `scripts/ops/fit_weather_demand.py` | [WEATHER_DEMAND_MODEL_OPERATOR.md](../operations/WEATHER_DEMAND_MODEL_OPERATOR.md) |

Scheduled sources get retries, freshness SLAs (on time, late, stale) and run history in
Source Center. ECMWF, National Gas and the operator imports still run as scripts: schedule
them with cron or the Windows Task Scheduler.

## Keep it healthy

Backups and restore drill (`backup_runtime.py`, `backup_restore_drill.py`), retention
(`prune_audit_events.py`, `prune_runtime_data.py`), stale jobs (`recover_stale_jobs.py`),
health at `/api/health/ready`, metrics at `/api/runtime/metrics`. Operations index:
[docs/operations](../operations).

## Market-data licences

The firm, not each user, holds market-data licences. Record every licence under
Administration → Access → Catalogue → Market-data licences (vendor, source family,
enterprise, site or named-user, display or non-display use, validity, seats). A licensed
data scope (EEX, ICE_ENDEX, TRAYPORT, ...) can then be granted to a person only when an
active licence covers their office and, for named-user licences, a seat is free. The holder
list is the usage report a vendor asks for in an audit. Vendor API credentials are stored
once on the server (Administration → Credentials), never in personal preferences.

## Single sign-on

OIDC (Entra ID, Okta, Ping, Keycloak) is configured directly; SAML, Kerberos and vendor SSO
agents in a dedicated network go through an authenticating gateway. Both map groups to roles
and data scopes the same way. See [ENTERPRISE_SSO.md](../operations/ENTERPRISE_SSO.md).

