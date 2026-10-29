# National Gas REST demand ingestion

Run from the repository root with the project installed, or set `PYTHONPATH=src`
for a source checkout. Migrate the configured database to the current Alembic
head before persistence. This command does not create schema or activate feeds.

PowerShell source-checkout dry run:

```powershell
$env:PYTHONPATH = 'src'
.venv/Scripts/python.exe scripts/ops/ingest_national_gas_rest.py --date-from 2026-10-26 --date-to 2026-10-27 --ids PUBOB637 --dry-run
```

The window selects publication dates, so returned revisions may refer to earlier
gas days. Supported IDs are PUBOB637 (D+1) and PUBOB652 (D+6). A window is bounded
to31days. D+6 is not automatically final. Dry-run reports source hashes, counts,
actual receipt and timestamp-evidence basis without writing a database.

For persistence, configure the existing database URL through the project's normal
runtime configuration and omit `--dry-run`. Avoid putting credentials in command
arguments or copied logs. The command appends immutable REST revisions in one
transaction, preserves first receipt on replay and refuses conflicting content.
It prints safe counts rather than the database URL or raw provider errors.

Root verification: actual public two-day PUBOB637 dry-run returned17 revisions;
the parser/persistence PostgreSQL probe inserted17 then replayed with0 inserts
and17 duplicates. Ten CLI tests cover validation, dry-run isolation, transaction
commit/rollback and error redaction. Provider-clock upper-bound evidence is
separate from actual receipt and does not itself authorize historical OOS use.

