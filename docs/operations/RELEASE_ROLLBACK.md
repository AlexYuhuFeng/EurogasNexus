# Release Rollback

## Golden rule

"Install the previous version" is only valid after schema compatibility has
been verified. Never promise rollback from a version whose migration cannot
support the previous binary.

## Current compatibility contract

- Migrations are expand-only within the current release line. CR-09/CR-10/CR-11
  additions use new columns with server defaults and new tables, so previous
  application code can generally continue serving against the newer schema.
- If a future migration removes or renames columns, it must be a two-phase
  EXPAND → application transition → CONTRACT release.

## Before rollback

1. `python scripts/release/compatibility_check.py` — verify current binary,
   permission registry, and OpenAPI path resolution.
2. `python scripts/ops/migration_preflight.py --json` — verify DB reachable,
   current revision readable, required tables present.
3. Confirm the target previous image/tag still passes `scripts/release/
   smoke_release.py` against a **read-only or restored copy** of the current
   schema before routing production traffic.

## Rollback steps

1. Stop or drain the failing release container/tag.
2. Start the previous validated image/tag.
3. Run liveness and readiness:
   ```bash
   python scripts/release/smoke_release.py --base-url <base>
   ```
4. Run `alembic current` and confirm the schema is in the expected compatibility
   range.
5. Resume workers only after the API smoke passes.
6. Record the rollback in `audit_events` (operator action) and update the
   release notes.

## Rollback with data-destructive migration

If the failed release already ran a destructive migration, do **not** roll
back the binary. Restore the pre-migration backup:

1. identify backup timestamp;
2. restore into an isolated target with `backup_restore_drill.py`;
3. validate revision/tables/business rows;
4. cut over to the restored database and previous binary.

## Unsafe rollback actions

- Do not run `alembic downgrade` without a reviewed, tested downgrade path.
- Do not route production traffic to an untested previous binary.
- Do not delete the failed release logs/audit events.
