# Incident Response

This runbook is a local-drill template. It does not replace the
deployment-owner security acceptance or a real incident-response exercise on
the target deployment.

## Roles

- Operator: owns the runtime and executes recovery commands.
- Reviewer: validates evidence and approves status changes.
- Deployment owner: accepts residual risk and sign-off.

## Incident classes

| Class | Example | First response |
| --- | --- | --- |
| Database unavailable | PostgreSQL container down / disk full | Stop dependent workers, preserve logs |
| API unavailable | container crash / bad config | Capture container logs before restart |
| Authentication compromise | identity key suspected leaked | Revoke key, rotate secrets, audit events |
| Data corruption / failed migration | bad Alembic migration | Stop migrations, restore from backup |
| Credential loss | lost encryption key | Rotate provider keys, restore from known-good env/backup |
| Release rollback | bad API deploy | Roll back image/tag and validate health |

## General response procedure

1. **Identify** – confirm the affected surface and impact.
2. **Contain** – stop ingestion/monitoring workers if they depend on the
   failed service.
3. **Preserve evidence** – copy logs, container status, and audit events.
4. **Restore or roll back** – use `scripts/ops/backup_runtime.py` and
   `pg_restore`, or redeploy the previous API image.
5. **Verify** – run:
   ```bash
   python scripts/ops/validate_runtime_db.py --json
   python -c "from apps.api.main import app; print('app import ok')"
   ```
6. **Notify** – report to deployment owner without exposing secrets.
7. **Post-incident** – update this runbook and the security acceptance evidence.

## Backup/restore drill checklist

- [ ] A real `pg_dump --format=custom` backup was produced.
- [ ] The dump was restored into a fresh PostgreSQL database.
- [ ] `alembic current` matches the intended release.
- [ ] `scripts/ops/validate_runtime_db.py --json` reports all required tables.
- [ ] API health endpoint reports `status=ok`.
- [ ] Provider credentials still decrypt with the correct secret key.
- [ ] No secret material was logged.

## Local drill

```bash
# 1. create a scratch database URL
export RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://nexus:nexus@127.0.0.1:55432/nexus_restore

# 2. restore from a dump
pg_restore --clean --if-exists --dbname=nexus_restore ./nexus-runtime-*.dump

# 3. validate
python scripts/ops/validate_runtime_db.py --json
```
