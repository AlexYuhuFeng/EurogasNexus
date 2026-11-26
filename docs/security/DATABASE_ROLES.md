# Database roles and the audit trail

Security review 2026-11 finding H5. The application used to connect to PostgreSQL as the
database owner, so it could rewrite or delete its own audit trail. This page sets up separate
roles and explains how the audit trail is protected.

## Roles

| Role | Used by | May |
|---|---|---|
| `eurogas_owner` | the `migrate` service; the dual-controlled audit prune | own the schema; run migrations |
| `eurogas_app` | the API and every worker | read and write business tables; **INSERT only** on `audit_events`, `audit_chain` and `audit_chain_anchors` |
| `eurogas_reader` | reporting (Excel, BI, a replica) | read business tables, never credentials, sessions or second factors |
| `eurogas_auditor` | compliance exports | read the audit trail only |

## Setting them up (existing installation)

1. Back up the database (`scripts/ops/backup_runtime.py`).
2. Run the migrations to head (they add the audit chain tables and the guard triggers).
3. As the PostgreSQL superuser, run `deploy/runtime/database_roles.sql`:

   ```sh
   psql "$ADMIN_URL" -v owner_password="'<secret>'" -v app_password="'<secret>'" \
        -v reader_password="'<secret>'" -v db=eurogas -f deploy/runtime/database_roles.sql
   ```

4. In the compose environment file set `EUROGAS_NEXUS_OWNER_DB_USER=eurogas_owner`,
   `EUROGAS_NEXUS_OWNER_DB_PASSWORD`, `EUROGAS_NEXUS_APP_DB_USER=eurogas_app` and
   `EUROGAS_NEXUS_APP_DB_PASSWORD`. `migrate` connects as the owner, every other service as the
   application role. Until these are set both fall back to `POSTGRES_USER`.
5. Restart and check `GET /api/health/ready` and `python scripts/ops/verify_audit_chain.py`.

The application works with the restricted role: it never updates or deletes an audit row. The
chain is kept in its own table (`audit_chain`), one inserted link per audit row, so sealing a
row is an insert too.

## Protections, layer by layer

1. **Grants**: the application role has no UPDATE, DELETE or TRUNCATE on the audit tables.
2. **Triggers** (migration 0095, PostgreSQL): any UPDATE of `audit_events` or `audit_chain`
   is refused, and a DELETE only inside a transaction that set
   `eurogas.audit_prune = 'approved'` (the prune function does this). This holds even where the
   roles are not yet split.
3. **Hash chain**: each committed audit row gets a link with the next sequence number, the
   previous link's hash and `SHA-256(previous hash || canonical row)`. Sealing happens inside
   the writing transaction, just before commit, under an advisory lock taken after the
   transaction's own statements. `GET /api/audit/verify` (administrators) and
   `python scripts/ops/verify_audit_chain.py` recompute the chain and name the first break: an
   edited row, a removed row or link, a forged link.
4. **Anchors**: `POST /api/audit/checkpoint` (or `verify_audit_chain.py --checkpoint`) records a
   digest of the chain head, signed with the deployment key; export it daily to a WORM store or
   the SIEM, so a rewrite of the whole chain by the database owner is detectable too.
5. **SIEM**: `EUROGAS_NEXUS_AUDIT_SINK` forwards every sealed row as one JSON line, with its
   sequence and hashes: `stdout`, `file:/path`, `syslog://host:port` (UDP, RFC 5424, facility
   13) or an `https://` webhook (NDJSON). Forwarding never fails the audited change.

## Retention and pruning

- Retention is `EUROGAS_NEXUS_AUDIT_RETENTION_DAYS` (default 1827 days, five years; at least
  365). Nothing younger is ever pruned.
- A dry run (`POST /api/audit/prune` with `dry_run: true`) counts what would go.
- A deletion is dual-controlled: the request answers 409 `dual_control_required`; a second
  administrator approves it under Admin, Access (pending approvals); the requester repeats the
  call with `X-Eurogas-Dual-Control: <change_id>`. With the roles split, the deletion is run by
  the owner role: `python scripts/ops/prune_audit_events.py --retention-days 1827 --commit
  --approved-change <change_id>` with the owner's database URL.
- Only the oldest contiguous part of the chain is removed; the last removed link is kept as a
  prune anchor, so the rest still verifies. The prune itself is audited.
- The internal profile's token can no longer delete audit rows.
