# Cost Observation Sources

This runbook describes how to schedule periodic refresh of route/entry-exit/
LNG cost observations.

## Prerequisites

The machine-readable JSON source must expose a list of objects matching the
cost-observation JSON schema:

- `id`
- `scope_type`
- `scope_id`
- `observation_type`
- `value`
- `currency`
- `unit`
- `effective_from_utc`
- `effective_to_utc`
- `source_system`
- `source_reference`

## One-off refresh

```bash
python scripts/ops/refresh_cost_observations.py \
  --url https://approved.example.test/cost-observations.json \
  --source-system TSO_TARIFFS
```

## Scheduled refresh examples

### Linux systemd timer

```ini
# /etc/systemd/system/eurogas-cost-refresh.service
[Service]
Environment=EUROGAS_NEXUS_COST_SOURCE_URL=https://approved.example.test/cost-observations.json
ExecStart=/usr/bin/python3 /opt/eurogas/scripts/ops/refresh_cost_observations.py
```

```ini
# /etc/systemd/system/eurogas-cost-refresh.timer
[Timer]
OnCalendar=daily
Persistent=true
```

### Windows Task Scheduler

Run daily:

```text
powershell.exe -Command "$env:EUROGAS_NEXUS_COST_SOURCE_URL='https://...'; python scripts/ops/refresh_cost_observations.py"
```

## Freshness monitoring

The repository exposes:

```text
cost_observation_freshness(session, scope_type, scope_id, now_utc)
```

and the API returns source provenance. A scope with no observations is
reported as `unavailable`; stale rows are never treated as current.
