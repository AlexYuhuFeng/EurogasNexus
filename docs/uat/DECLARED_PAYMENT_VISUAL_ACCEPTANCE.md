# Declared-payment visual acceptance fixtures (isolated PostgreSQL)

Status: preparation for the open real-browser acceptance recorded in the
Architecture V2 execution checkpoint. **Creating these fixtures is not UI
acceptance.** EN/ZH parity and desktop/mobile rendering still require a human
in a real browser at the running web client; this document adds no product
behaviour and changes no runtime default.

## 1. What the fixture is

`scripts/uat/seed_declared_payment_uat_fixture.py` seeds two clearly synthetic
upstream contracts with declared `contract-payment-terms/v1` schedules into an
explicitly isolated PostgreSQL database, through the existing repository
fixture path (`upsert_upstream_contract`, the documented fixtures/seeding entry
point) and the canonical domain decoder (`ContractPaymentTerms` /
`PaymentScheduleItem` / `ExplicitPaymentDate` / `AnchoredPaymentRule`), so no
payment-term semantics are re-implemented in the script.

| Contract id | Schedule shape |
| --- | --- |
| `uat-declared-payment-explicit-dates-v1` | three explicit final payable dates, mixed INFLOW/OUTFLOW, long synthetic evidence |
| `uat-declared-payment-anchored-rules-v1` | three anchored rules whose anchor dates stay unresolved (calendar count, business-day count, `FOLLOWING` / `MODIFIED_FOLLOWING` rolls), mixed INFLOW/OUTFLOW, long synthetic evidence |

Every identifier, contract name and evidence string states that it is
synthetic: no real contract, invoice, note, calendar or counterparty document
is represented. Nothing resolves a payable date, values cash, or touches
execution, nomination or settlement. Re-running the script is idempotent for
its own ids; it never modifies `preview-portfolio-contract-ttf-pool-2025` or
any other stored contract.

Honest limits of the seeded rows: the repository fixture path writes the
contract row and its canonical declared terms only, so the two fixtures carry
no captured revisions and no audit rows. Revision-history screens are not
exercised by this fixture.

## 2. Safety gates (configuration and pre-write target refusals write nothing)

Exit code 2 (configuration/usage):

- `EUROGAS_NEXUS_ENV` is `trial` or `release`;
- `EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED` is not `1`;
- `RUNTIME_STORE_DATABASE_URL` is unset - the script never falls back to
  `DATABASE_URL` or `EUROGAS_NEXUS_DB_DSN`, so a default runtime store is never
  inherited by accident;
- the URL is not PostgreSQL (no SQLite, no in-memory store);
- the database name is the default runtime database `eurogas_nexus`, names no
  database, or does not start with `eurogas_uat_payment_`;
- an unknown command-line argument is supplied.

Exit code 3 (target refusal, nothing written):

- the target lacks the reviewed schema (`upstream_resource_contracts`, or its
  `payment_terms_json` carrier) - apply the reviewed migrations to the isolated
  database first; the script never migrates or creates a database;
- the target already holds any upstream contract record outside this fixture's
  own `uat-declared-payment-` ids - the contamination guard for shared
  databases.

Exit code 4: the isolated database operation or read-back verification failed.
Rows may already be committed if read-back failed; inspect the isolated target
before retrying. The message is sanitized and the connection URL is never printed.

The script prints only the target database *name*, the seeded ids and the
decoded item counts. It does not create identities, weaken authentication,
call network providers, or write to a runtime database. It is not listed in
`scripts/release/package_deployment_bundle.policy.json`, so it cannot enter the
customer Server bundle.

## 3. Safe setup / use / cleanup

Setup (operator, on an isolated host; do not reuse `eurogas_nexus` or the
commercial UAT scratch database):

1. Create a dedicated PostgreSQL database whose name starts with
   `eurogas_uat_payment_`, for example `eurogas_uat_payment_visual_20261006`.
2. Apply the reviewed migrations to it: `alembic upgrade head` with
   `RUNTIME_STORE_DATABASE_URL` pointing at that database.
3. Optionally seed a browser identity with the existing
   `scripts/uat/seed_browser_identity.py` (separate gate; this fixture does not
   create principals).

Seed:

```bash
EUROGAS_NEXUS_ENV=development \
EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED=1 \
RUNTIME_STORE_DATABASE_URL=postgresql://<user>@<host>:5432/eurogas_uat_payment_visual_20261006 \
python scripts/uat/seed_declared_payment_uat_fixture.py
```

The contamination guard refuses a target that already holds any contract
outside the fixture's own ids, so run this script before any other seed script
that inserts contracts into the same database (or give it its own database).

Then start the normal development runtime against the same isolated database
and open Portfolio > Resources > Terms > Settlement and cash, loading each
`uat-declared-payment-...` contract from the Library.

Cleanup (fixture-scoped; never run against a shared or runtime database):

```sql
DELETE FROM upstream_contract_revisions WHERE contract_id LIKE 'uat-declared-payment-%';
DELETE FROM audit_events WHERE resource LIKE 'upstream_contract:uat-declared-payment-%';
DELETE FROM upstream_resource_contracts WHERE contract_id LIKE 'uat-declared-payment-%';
```

The simpler and preferred cleanup is dropping the whole disposable database.

## 4. Visual acceptance still open

Seeded fixtures are preparation, not evidence. The following remain open and
must be performed by a human in a real browser against the running web client,
in EN and ZH, with measured viewports (actual CSS pixels, not requested window
sizes):

- both declared schedules render in the Settlement-and-cash payment panel with
  correct labels in both languages;
- unresolved anchored rules display the "not a calculated payable date"
  disclosure, and the long evidence strings wrap without overlap;
- desktop and mobile widths are checked and recorded (screenshot or DOM
  measurement plus the measured viewport);
- the absence state (a contract with no declared terms) remains clearly
  distinct from a declared schedule.

Automated checks in `tests/uat/test_declared_payment_uat_fixture.py` cover only
the guard refusals and the fixture/domain validity; they assert nothing about
the rendered UI.
