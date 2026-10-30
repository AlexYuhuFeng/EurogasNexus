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
| ENTSOG, GIE, ECB | Data-ops scheduler (`scripts/ops/run_dataops_scheduler.py`) | Source Center |
| BoE SONIA, NY Fed SOFR | `scripts/ops/ingest_interest_rates.py` | [INTEREST_RATES.md](../operations/INTEREST_RATES.md) |
| ECMWF temperature | `scripts/ops/ingest_ecmwf_forecasts.py` | [ECMWF_FORECAST_OPERATIONS.md](../data/ECMWF_FORECAST_OPERATIONS.md) |
| National Gas demand | `scripts/ops/ingest_national_gas_rest.py` | [NATIONAL_GAS_REST_OPERATIONS.md](../data/NATIONAL_GAS_REST_OPERATIONS.md) |
| ENTSO-E power | `scripts/ops/ingest_power.py` | [POWER_DATA.md](../operations/POWER_DATA.md) |
| Licensed quotes, FX fixings | `scripts/ops/import_market_quotes.py`, `import_fx_fixings.py` | [LIVE_PRICE_SOURCES.md](../operations/LIVE_PRICE_SOURCES.md), [FX_FIXINGS.md](../operations/FX_FIXINGS.md) |
| Weather-demand model | `scripts/ops/fit_weather_demand.py` | [WEATHER_DEMAND_MODEL_OPERATOR.md](../operations/WEATHER_DEMAND_MODEL_OPERATOR.md) |

Schedule the script-run sources with cron or the Windows Task Scheduler until they move
under the data-ops scheduler.

## Keep it healthy

Backups and restore drill (`backup_runtime.py`, `backup_restore_drill.py`), retention
(`prune_audit_events.py`, `prune_runtime_data.py`), stale jobs (`recover_stale_jobs.py`),
health at `/api/health/ready`, metrics at `/api/runtime/metrics`. Operations index:
[docs/operations](../operations).
