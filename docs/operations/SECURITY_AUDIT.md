# Security Audit Runbook

## Read path

- Admin: `GET /api/audit` (filterable by actor/action/resource/outcome).
- Internal profile: `GET /api/internal/audit/events`.

## Retention

Default 365 days, allowed 30-3650. Pruning is dry-run by default:

```bash
python scripts/ops/prune_audit_events.py --retention-days 365
python scripts/ops/prune_audit_events.py --retention-days 365 --commit
```

## Append-only rules

No application API updates or deletes audit events. Admin reads only.
Audit rows never contain tokens, key secrets, provider credentials, raw
licensed payloads, or full financial content.

## Verification

Create/change an identity, freeze a strategy, change a credential, or run a
backfill and verify the matching `action`, `permission`, `correlation_id`, and
before/after summary appear.

## Escalation

If a sensitive action has no audit row, treat it as a security incident and do
not rely on application logs alone.
