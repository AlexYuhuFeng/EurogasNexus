# Support, bug reports and updates

## Supported platforms

| Client | Supported |
|---|---|
| Web | Current and previous major version of Chrome, Edge, Firefox and Safari on desktop; 1440x900 and larger screens |
| Desktop | Windows 10 and 11 (x64) installer; macOS and Linux builds where the release lists them |
| Python SDK | Python 3.11 to 3.13 |
| Server | Linux x64 container or Python 3.11+ with PostgreSQL 15+ |

## Reporting a problem

1. **Settings → About & Diagnostics**, then copy or save the diagnostics bundle. The bundle holds the
   client and server versions, the release channel, which sources are stale or failing
   and recent request failures. It is built from an allowlist: no prices, positions,
   contract terms, credentials or personal data.
2. Note what you did, what you expected and what you saw, and the time (UTC).
3. Send both to the firm's IT desk. IT adds the server log lines for that time
   (`request_id` is in each failed response) and forwards to the vendor support channel
   named in the support agreement.

Severity used by support: **P1** nobody can sign in or the server is down; **P2** a
workflow is blocked (no positions, a source down) with no workaround; **P3** wrong or
unclear output with a workaround; **P4** cosmetic or a request.

A figure that looks wrong is worth reporting even if you are unsure: every number in the
product names its source and as-of time, so support can trace it.

## Updates

* The firm's IT desk decides when to update; nothing updates itself (see
  [UPDATE_POLICY.md](../release/UPDATE_POLICY.md)). Desktop installers upgrade in place and
  keep settings; uninstall removes the program but not the firm's database.
* Each release publishes the installer, the server image, `SHA256SUMS`, a release
  manifest, SBOMs and provenance attestations. IT verifies the checksum before rollout.
* The web client and the server must be the same minor version; the client warns when
  they are not.
* Database changes run as migrations (`alembic upgrade head`) with a preflight check and
  a backup first (see [DB_MIGRATIONS.md](../operations/DB_MIGRATIONS.md) and
  [RELEASE_ROLLBACK.md](../operations/RELEASE_ROLLBACK.md)).
* Release notes say what changed for each role.
