# Book isolation and the commercial-data boundary

Security review 2026-11 findings H1 and H2. This page states what a person may read, where it
is enforced, and how an installation is configured.

## Who sees which books

Book isolation is **on by default** (`EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true`). A person sees
the books their data scopes name:

| Data scope | Books |
|---|---|
| `BOOKS:*` | every book, and positions not yet in a book (head office) |
| `BOOKS:ENTITY:<legal entity>` | the books of that legal entity, for example `BOOKS:ENTITY:NWG-NL` |
| `BOOKS:REGION:<region>` | the books of that region |
| `BOOKS:BOOK:<book id>` | one book |
| `*` | everything (service accounts and the all-roles administrator only) |
| none | no book |

Scopes come from the administrator (Admin, Access) or from SSO groups through
`EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP`. A personal API key carries at most its owner's scopes.

Isolation can be switched off only with `EUROGAS_NEXUS_PORTFOLIO_ISOLATION=false`. In a
`trial` or `release` environment the API then refuses to start unless the deployment also
declares `EUROGAS_NEXUS_SINGLE_BOOK_FIRM=true` (one office, no information barrier).

## Where it is enforced: one place

The scope is enforced in the ORM layer (`src/eurogas_nexus/db/book_scope.py`), not route by
route. Every SQLAlchemy session runs two events:

- `do_orm_execute` adds the caller's scope to every book-bearing table wherever it appears
  in a statement: the top level, joins, subqueries, column queries, `session.get`,
  relationship loads and ORM `UPDATE`/`DELETE`.
- `before_flush` refuses a write into a book outside the scope, and a new row with no book
  from a caller without head-office scope (403 `book_outside_scope`).

Tables covered:

- every table with a `book_id` column, automatically (a new table is covered on the day it
  is added);
- credit lines (by legal entity), trader mandates (by their books), hedge bands, daily
  deliveries, contract revisions and capacity profiles (by contract), cargo hedges and
  voyage terms (by cargo);
- decision cases and their records (by `portfolio_ref`, plus the author's own cases), and
  analysis snapshots (the author's own, plus those cited by a case the caller may read).

A request starts with a deny-all scope until its caller is identified, so a path that fails
before identification reads no book. Workers, the scheduler and command-line tools run
outside a request as the system and see every book; their results are filtered when a
person reads them. The machinery that reads across books on the firm's behalf sets that
explicitly with `portfolio_scope.system_scope()` rather than relying on an empty context:
the scheduler (`scripts/ops/run_dataops_scheduler.py`), the gated upgrade command
(`scripts/ops/upgrade_database.py`), the metrics exporter's database reads
(`api/middleware/metrics_endpoint.py`) and the API's live-update poller (`api/stream_hub.py`).
The poller is the one that serves people: what it reads passes each connection's own guard
(that user's book scope, licensed data scopes and commercial boundary) before it is sent
(`tests/security/test_stream_book_scope.py`, two legal entities on one poller;
`tests/security/test_background_scope.py` for the others).

`tests/security/test_book_scope_inventory.py` keeps this honest:

- every table with a book-like column must be scoped, delegated to a named module (rows that
  span several books: opportunities, market reports) or declared not book data with a reason;
- no raw SQL reads a scoped table outside the maintenance modules;
- a two-entity fixture fills every scoped table for two legal entities, and every GET route of
  the application is called by a principal with every commercial role but one entity's books;
  no response may carry the other entity's rows.

## Limits, credit and marks need a grant

Credit exposure, credit lines, trader mandates and their usage, hedge bands and firm marks
need the `risk.limits.read` permission. ANALYST (the front office) and REVIEWER (the risk
function) hold it. VIEWER, SCHEDULER and OPERATOR do not; an administrator grants it to one
person with the data scope `PERM:risk.limits.read`. OPERATOR (source operations) no longer
reads positions by role; `PERM:portfolio.read` grants it to one person. A `*` scope never
grants a permission.

The check sits in the limits service itself (`application/limits_service.py`), so Today,
explanations, discoveries and monitoring follow the same rule as the routes.

## Platform administration is not commercial access

The commercial-data boundary is **default-commercial**: every `/api/` path needs a commercial
capability unless it is platform, context or public-reference state listed in
`PLATFORM_PATH_PREFIXES` (`src/eurogas_nexus/security/permissions.py`): health, sign-in,
the caller's own settings, access administration, audit, provider credentials, sources,
runtime, the glossary, public network, flows, storage, weather, tariffs and LNG terminal
reference. A platform administrator without a commercial role therefore does not read
decision cases, analysis snapshots, data products, LNG cargoes or capacity bookings, nor any
family added later. `tests/security/test_commercial_boundary_h2.py` calls every commercial GET
route as such an administrator and expects 403.

## The signed ERP hand-off

`GET /api/decision-cases/{case_id}/handoff` signs a decided case for ERP or ETRM middleware.
It needs the review floor and a party to the decision: the case's author or a person who
recorded a decision on it.

## Demo server

The demo's testers carry explicit scopes (`scripts/demo/start_public_demo.py`,
`TESTER_SCOPES`), re-applied on every start: each trader sees their own legal entity's books
(`demo.trader` NWG-UK, `demo.nl.trader` NWG-NL), risk, management, analysts, finance,
compliance, origination and scheduling see every book, data operations and the platform
administrator see none, and the all-roles `tester` keeps `*`. Finance reads the books but not
credit or mandate limits.
