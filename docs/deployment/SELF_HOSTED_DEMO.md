# Self-hosted test and demo server

Eurogas Nexus on one machine with Docker, for the owner and invited testers: every product
feature usable, demo data marked simulated, signed in with a tester password. It is **not**
a customer runtime. The customer stack is `deploy/runtime/` (published, digest-pinned API
image built from `deploy/runtime/Dockerfile.api`, no demo data), delivered as described in
[DEPLOYMENT_ROLES-EN.md](DEPLOYMENT_ROLES-EN.md); nothing here changes it.

| Piece | Where |
|---|---|
| Demo image | `Dockerfile` at the repository root (context: the repository root). `docker build .` builds the demo image; the release workflow builds only `deploy/runtime/Dockerfile.api` |
| Stack | `deploy/demo/compose.yaml`: the demo image, PostgreSQL 16 with a named volume, an optional HTTPS front (Caddy) |
| Settings | `deploy/demo/.env.example`, copied to `deploy/demo/.env` (git-ignored, never in the image) |
| Port | `8080` in the container; published on `127.0.0.1:8080` by default |
| Health | `/api/health/live` (process), `/api/health/ready` (database reachable, schema current) |
| Version | `GET /api/runtime/release` (`git_sha`, `git_ref`; sign-in required) |
| Start-up | `scripts/demo/start_public_demo.py`: wait for PostgreSQL, `alembic upgrade head`, reference network, demo desk (seeded once, then rolled forward to the current gas day), tester identities, serve |

The root location is deliberate: the standard file is what `docker build .` and most tools
pick up, its header says it is the demo image and points to the customer one, and the
release tests (`tests/release/test_demo_image_boundary.py`) check that the release workflow
never builds it and that the customer image carries no demo payload.

## Requirements

Docker Engine 24+ with Compose v2 (Linux), or Docker Desktop (macOS, Windows). One free CPU
core and 1 GB of free memory are comfortable; see "Footprint" for measured numbers. The
build downloads the base images, npm and PyPI packages (lock files only), so the first
build needs internet access.

## Start it

Linux and macOS:

```bash
git clone <repository> eurogas-nexus && cd eurogas-nexus/deploy/demo
cp .env.example .env
# Fill DEMO_DB_PASSWORD, EUROGAS_NEXUS_SECRET_KEY and EUROGAS_NEXUS_DEV_LOGIN_PASSWORD:
python3 -c "import secrets;print(secrets.token_urlsafe(18))"          # passwords
python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"  # secret key
DEMO_GIT_SHA=$(git rev-parse HEAD) DEMO_GIT_REF=$(git rev-parse --abbrev-ref HEAD) \
  docker compose up -d --build
```

Windows (PowerShell, Docker Desktop running):

```powershell
git clone <repository> eurogas-nexus; cd eurogas-nexus\deploy\demo
Copy-Item .env.example .env   # then edit .env in a text editor and fill the three secrets
$env:DEMO_GIT_SHA = git rev-parse HEAD
$env:DEMO_GIT_REF = git rev-parse --abbrev-ref HEAD
docker compose up -d --build
```

On Windows keep the checkout's line endings as Git gives them (the repository declares LF);
do not open shell scripts in an editor that converts them.

Watch it come up with `docker compose logs -f demo`. Each step logs its time and the last
line is `[demo-start] start-up steps finished in …s; serving on port 8080`. Then open
<http://127.0.0.1:8080>.

The stack refuses to start without the secrets: Compose stops with
`required variable EUROGAS_NEXUS_DEV_LOGIN_PASSWORD is missing a value`, and the image itself
refuses a tester password shorter than 12 characters
(`[demo-start] FATAL: refusing to start: …`). Nothing is generated for you and no credential
has a default.

### The demo exchange feed (intraday, simulated)

While the demo is up, `scripts/demo/exchange_feed.py --continuous` (started by the demo start-up)
streams two-sided quotes with size, trade prints (screen and the odd block) and session
statistics (open/high/low, VWAP, volume, trade count, prior settlement) for **TTF and NBP, WD and
DA**, bursty and seconds apart (about one message a second, bursts of several a second, at most
four a second), on the demo market's own prices. It writes as `DEMO_Sim` through the same tick
ingestion a licensed feed adapter uses (`POST /api/market/ticks` / `application/market_ticks`:
validation, the source family's entitlement, the inputs-changed hook that evaluates tracked
strategies), and a simulated prompt trade is booked into the demo books every 15 minutes, so the
prompt market's performance figures move. Admin → Data feeds lists it as **Demo exchange feed
(simulated)** with its last message, rate and status, one status line a minute.

- **Hours**: 07:00-19:00 CET/CEST every day; outside them it pauses (and says so in its status).
- **Restart**: started again by every demo start; an advisory lock keeps one running.
- **Retention**: its quotes, prints, status lines and the booked simulated trades are kept for
  48 hours, pruned every ten minutes.
- **Who writes today's WD/DA**: the feed, while it runs. With it off the roll-forward's daily
  board snapshot stands alone.
- Every row is simulated and labelled; the customer image does not ship `scripts/demo`.

Planted prompt cases (CET/CEST, during trading hours), so a test session of any length finds them:

| Case | Where | Schedule | What is planted |
|---|---|---|---|
| `P1-ttf-wd-da` | TTF, WD vs DA | minutes 10-12, 30-32 and 50-52 of every trading hour | WD 0.60 EUR/MWh over DA (even hours) or under it (odd hours), on top of the usual drift |
| `P2-nbp-ttf-da` | NBP vs TTF, DA | 10:00-10:09 and 15:00-15:09 | NBP DA in EUR at the demo fixing 0.80 EUR/MWh above TTF DA plus the simulated BBL route cost (1.88); at all other times at least 0.30 below it |

## Settings

| Name | Purpose | Required |
|---|---|---|
| `DEMO_DB_PASSWORD` | Password of the stack's PostgreSQL (not published to the network) | yes |
| `EUROGAS_NEXUS_SECRET_KEY` | Encrypts stored provider keys, keys identity digests. Keep it stable | yes |
| `EUROGAS_NEXUS_DEV_LOGIN_PASSWORD` | The tester password, 12+ characters | yes |
| `DEMO_BIND_ADDRESS`, `DEMO_PORT` | Where the demo listens on the host (default `127.0.0.1:8080`) | no |
| `DEMO_SERVER_NAME`, `DEMO_TLS`, `DEMO_HTTPS_BIND_ADDRESS`, `DEMO_HTTPS_PORT` | The optional HTTPS front | no |
| `DEMO_GIT_SHA`, `DEMO_GIT_REF` | Build identity shown by `/api/runtime/release` | no |
| `DEMO_DATABASE_URL` | An external PostgreSQL instead of the stack's own | no |
| `EUROGAS_NEXUS_DB_SSL_ROOT_CERT` | CA for `sslmode=verify-full` (PEM text or a path in the container) | no |
| `EUROGAS_NEXUS_DEMO_RESET_TOKEN` | Change it to re-seed the demo on the next start | no |
| `EUROGAS_NEXUS_LLM_API_KEY` | Model key; turns AI on | no |
| `GIE_API_KEY`, `EIA_API_KEY`, `ENTSOE_SECURITY_TOKEN` | Public-source keys; any one turns live refresh on | no |
| `EUROGAS_NEXUS_DEMO_LIVE_SOURCES` | `auto` (on when a key is set), `on`, `off` | no |
| `EUROGAS_NEXUS_DEMO_CATCH_UP_MAX_DAYS`, `EUROGAS_NEXUS_DEMO_REFRESH_HOURS` | Catch-up bound (45 days) and refresh interval (6 h) | no |
| `EUROGAS_NEXUS_DEMO_EXCHANGE_FEED` | `on` (default) or `off`: the simulated intraday exchange feed | no |
| `EUROGAS_NEXUS_CORS_ORIGINS` | Only if saving fails with `origin_not_allowed` | no |

The image sets the rest: `EUROGAS_NEXUS_ENV=development` (the demo seed refuses trial and
release), `EUROGAS_NEXUS_API_PROFILE=demo`, the tester user names, demo marks on, AI on only
with a model key, a connection pool of 8 + 4 with up to 15 s to wait for a connection (a
desk page fires about 28 reads at once; 3 + 2 with a 5 s wait refused them or let them pass
the browser's 10 s timeout during a catch-up round), and a random deployment API token
nobody knows, so the SDK token path is closed and browsers sign in instead.

## Sign in

In the panel titled **Tester sign-in**, type a user name and the tester
password:

| User name | Role | Job functions | Shows |
|---|---|---|---|
| `tester` | ADMIN, ANALYST, OPERATOR, REVIEWER | all | everything |
| `demo.trader` | ANALYST | Trader (NBP book) | desk, deals, own mandate |
| `demo.nl.trader` | ANALYST | Trader (TTF book) | desk, deals, own mandate |
| `demo.analyst` | ANALYST | HQ business analyst, quant researcher | research, strategy |
| `demo.risk` | REVIEWER | Risk manager | limits, review; can change credit lines |
| `demo.manager` | REVIEWER | Management, reviewer | overview, review |
| `demo.finance` | VIEWER | Finance and settlement | read-only book views |
| `demo.compliance` | REVIEWER | Legal and compliance | review, decision record |
| `demo.ops` | OPERATOR | Data operator | Source centre, ingestion runs |
| `demo.originator` | ANALYST | Originator | deals: evaluate, routes and cargo bids, contracts |
| `demo.operations` | SCHEDULER | Operations (deliveries, scheduling) | delivery, nomination deadlines, outages; records nomination and terminal-step status (nothing is sent) |
| `demo.admin` | ADMIN | Platform administrator | users, keys, audit; no commercial data, by design |

Every feature works, writes included (contracts, scenarios, optimisation, reviews, limits,
the Source centre, administration, AI with a model key, live data with keys). Never
possible, because the product has no such function: trade execution or order entry,
nomination submission, settlement or payment. Demo figures carry **Demo data** in the top
bar and `sim` beside each value.

The demo keeps its own events current: at start and then every hour it rolls the demo series
forward (the fictional unplanned outage is revised every five hours, so the situational strip
under the top bar always has a live, `sim`-marked item for the roles it concerns) and runs one
monitoring scan with the demo's configuration, so the alerts bell and the strip agree with the
risk pages.
The first-run setup guide is recorded as "configured by the demo profile" at start-up, so it
does not open at sign-in; administrators reach it from Admin → Access & Identity → Setup.

### Demo test accounts (optional)

For a public demo the owner can add simple sign-in names, each with its own password, with
`EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS` in `deploy/demo/.env` (the example file lists the nine
below, commented out):

```
EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS=test_trader:12345678,test_nl_trader:12345678,test_analyst:12345678,test_risk:12345678,test_manager:12345678,test_finance:12345678,test_compliance:12345678,test_ops:12345678,test_admin:12345678:admin
```

| Name | Copies | Role |
|---|---|---|
| `test_trader` | `demo.trader` | ANALYST, Trader (NBP) |
| `test_nl_trader` | `demo.nl.trader` | ANALYST, Trader (TTF) |
| `test_analyst` | `demo.analyst` | ANALYST |
| `test_risk` | `demo.risk` | REVIEWER, Risk manager |
| `test_manager` | `demo.manager` | REVIEWER |
| `test_finance` | `demo.finance` | VIEWER |
| `test_compliance` | `demo.compliance` | REVIEWER |
| `test_ops` | `demo.ops` | OPERATOR |
| `test_admin` | `demo.admin` | ADMIN (only because the entry says `:admin`) |

They are local accounts created at start-up through the product's own local-account code
(re-applied on a reset, their password restored at every start, disabled when removed from
the list), sign in on the same form as the testers, and need no password change. The form is
`name:password[:admin]` separated by commas, or a JSON list
`[{"username": "desk_one", "password": "...", "as": "demo.trader"}]` (`as` names the tester
whose roles to copy; required for a name not in the table). An entry whose tester holds ADMIN
is refused unless it is marked `:admin` / `"allow_admin": true`.

**Warning.** These passwords may be shorter than the product's 12-character policy - that is
the point of the setting - so **anyone who knows them can sign in**. The start-up log says so
on every start (`WARNING: demo test accounts with a weak shared password are enabled`). Use it
only on a demo server with fictional data. A customer server refuses it: the API does not start
with the setting, preflight reports it, and these accounts never sign in on a server that is
not the demo profile. Five wrong passwords lock a test account for 15 minutes (anyone can do
that to a public name); a restart or a tester with `tester`'s administrator rights unlocks it.

## The demo market

Every demo hub (TTF, NBP, THE, PEG, ZTP, PSV, CEGH, PVB, ETF, GTF) is quoted for every product
the board and the instrument catalogue know: WD, DA, WE, BOM, the next twelve months, four
quarters, two seasons (Sum/Win) and two calendar years. Quotes are two-sided, in the hub's own
quotation (NBP in p/th, the others in EUR/MWh), on its tick (0.01 p/th, 0.005 EUR/MWh), with a
width that depends on the hub and the product. 400 days of daily closes are kept for WD, DA, WE,
BOM, Q+1, S+1 and Cal+1 (and the existing month-ahead), plus 30 days for each dated quarter,
season and year, so backtests and z-scores have history. Instrument ids follow the catalogue:
`TTF:DA`, `TTF:Q1-27`, `TTF:Win-27`, `TTF:Cal-28`.

The market is derived from the month-ahead history the demo already keeps, so it is coherent by
construction: each month is the hub's seasonal curve plus that day's move; a quarter, season or
year is the day-weighted average of its months (to the tick); DA mean-reverts to the front month
(continental hubs share TTF's prompt move plus a small one of their own); WD sits near DA, and WE
and BOM each follow DA with a small, bounded process of their own. The hubs of the market-area
graph (TTF, THE, PEG, ZTP, NBP) are held inside the band no route can arbitrage at the simulated
transport costs (TTF the reference), so a locational spread nets below its cost unless planted.
The monthly forward curve the ladder marks at and the Prices screen draws is the same market on
the day of its snapshot: its front month is the hub's newest month-ahead close (what Today and
the reports show) and every later month is priced as above, with a small month-on-month
backwardation so no two years repeat. Draws come from separate named streams
(`scripts/demo/demo_market.py`), so the other demo series are unchanged. Everything is
`DEMO_Sim`, marked simulated, and the roll-forward extends it day by day. It exists only in the
demo image; the customer runtime does not ship `scripts/demo`.

**Today's prompt.** On gas day D the desk reads D's prompt market: the board quotes WD for gas
day D and DA for the next day the market quotes (Monday's on a Friday; the weekend is WE). Every
roll-forward (at start-up and hourly) writes one snapshot of WD and DA, two-sided with a size and
a running "last", and the curve once a day. While the demo exchange feed quotes (it is on unless
`EUROGAS_NEXUS_DEMO_EXCHANGE_FEED=off`; 07:00-19:00 CET/CEST) it owns today's TTF and NBP WD and
DA quotes and the roll-forward writes the other hubs'; outside those hours, or with the feed off,
the roll-forward writes them all, so the board is quoted overnight too.

**Evaluation on the demo.** The demo image runs no data-operations scheduler, so the seed and
every roll-forward note the input classes they changed and run the scheduled opportunity
evaluation themselves (`evaluate_demo_desk`). An item is listed after two consecutive
evaluations (the persistence rule): after a fresh start, at the second roll-forward.

**What a volume seeded by an older build gets.** The roll-forward tops up what a newer seed adds
and the store lacks (`ensure_demo_fixtures`): the simulated tariffs, the case awaiting review,
credit lines, mandates, routes, the approved hedge bands of the demo contracts that still exist
(a contract a tester removed is not re-added, nor its band), the firm storage at CEGH
(`demo-storage-cegh`, fictional) and the demo assumption set (`Demo desk assumptions`, approved:
`storage.capacity_fee` 2.80, `storage.injection_fee` 0.50, `storage.withdrawal_fee` 0.50 EUR/MWh,
together the 3.80 the time-spread cases are measured against).

**Simulated tariffs.** One crossing of each main hub pair, both directions: TTF-NBP through BBL
(1.88 EUR/MWh forward, 1.80 reverse), TTF-THE at VIP TTF-THE-H (1.00), TTF-ZTP at Zelzate (0.85;
1.65 back), THE-PEG at Obergailbach (1.05), THE-ZTP at VIP THE-ZTP (1.40), PEG-ZTP at Virtualys
(0.90), ZTP-NBP through IUK (3.72; 3.75 back). Invented, `SIMULATOR_ONLY`, read on a demo desk
only, and retired leg by leg once a published row names the same operator, point and direction.

Planted dislocations (and no others) give the opportunity evaluators something true to find:

| Case | Found as | Where | What is planted |
|---|---|---|---|
| `L1-nbp-over-ttf-da` | market L (TTF -> NBP via BBL) | NBP vs TTF, DA | NBP DA (in EUR at the demo fixing) over TTF DA exceeds the simulated BBL route cost (1.88 EUR/MWh) by 1.20 on days with ordinal % 23 in {0, 1}; on every other day the band keeps the net at least 0.65 below the cost. Only TTF reaches it: every other hub's route through TTF nets below zero |
| `W1-ttf-wd-over-da` | market P (TTF WD over DA) | TTF, WD vs DA | WD 1.50 over DA on days with ordinal % 17 = 5; elsewhere, and at every other hub, \|WD - DA\| <= 0.25 |
| `T1-cegh-winter-over-summer` | market T; book T on the demo storage at CEGH | CEGH, Sum vs Win | A 1.00 EUR/MWh far-winter premium on winter months 6+ months ahead, so its next winter over the summer before exceeds the storage cost (3.80 EUR/MWh); every other hub stays below. Standing: found every day |
| `O1-nbp-outage-basis` | E (event exposure, must act) | NBP, DA | +0.60 EUR/MWh on NBP DA while the demo's unplanned NBP-zone outage is active, inside the band on non-planted days; the outage's cut to the demo contracts is the E item |
| `S1-open-gas-day` | S (sell-down, must act), the day before | UK book at NBP, NL book at TTF, next gas day | On gas days 18 to 20 of each month the industrial offtake falls to 9,000 MWh (UK long at NBP) and the NL storage injection rises to 7,000 MWh (NL short at TTF); every other gas day the demo schedule balances each book within its band (outages in force). The UK book's TTF residual, left after the BBL export, has no TTF rate and is a "cannot evaluate", not listed |
| `R1-lesser-rule-at-nbp` | a lesser-rule break in the gas day's reconciliation (SCHED-1; not an opportunity), alerted to operations within 3 hours of the cut-off | UK book at NBP, gas days 11 and 12 of each month | The UK book's bilateral sale to Aldermoor (6,000 MWh a day) is nominated in full, but Aldermoor nominated 4,800 MWh and the demo TSO confirmed the lesser: 1,200 MWh cut, the UK book long by that (indicative cash-out 1,440 GBP at the demo discount). On every other gas day the sale, and each simulated prompt trade as it is booked, is nominated and matched in full, so the reconciliation is quiet |

Not planted but true of the demo every day: the hedge gap of the Haldor contract (G), the
outage exposures (E), and, on most days, the held BBL capacity TTF -> NBP (C: charges sunk, so
NBP's premium inside the band is worth capturing), plus book T "storage not held" month pairs
(watching) where a curve's seasonal swing exceeds the stated cost. WE and BOM are not planted.

The cases are also in `PLANTED_CASES` in `scripts/demo/demo_market.py`, and the closes and quotes
they touch carry `demo_planted_case` in their metadata. `tests/unit/test_demo_market.py` checks
that each holds on exactly its days; `tests/integration/test_demo_planted_cases.py` seeds a fresh
store at 09:00 on an L1 day, a W1 day, the day before an S1 gas day, the day before an R1 gas
day and a quiet day, evaluates twice and asserts the exact set listed; it also reads the
reconciliation in the evening of the R1 eve and the quiet day and finds the one R1 break only.

## Reaching it from other devices

The demo port is bound to `127.0.0.1`. Do **not** publish it on a router or set
`DEMO_BIND_ADDRESS=0.0.0.0` on a machine reachable from the internet: it would expose a
sign-in page over plain HTTP. Choose one of:

1. **HTTPS front on the local network** (the `deploy/runtime/` Caddy pattern):
   `docker compose --profile https up -d`. Caddy listens on port 443 and proxies to the demo.
   With `DEMO_TLS=internal` Caddy issues a certificate from its own local CA: set
   `DEMO_SERVER_NAME` to the name devices use (for example `demo.lan`, resolvable on your
   network), and either trust Caddy's root certificate on each device
   (`docker compose cp gateway:/data/caddy/pki/authorities/local/root.crt .`) or accept the
   warning. Restrict `DEMO_HTTPS_BIND_ADDRESS` to the LAN interface's address if the machine
   has several.
2. **A private tunnel or overlay network** (for example a WireGuard/Tailscale-style VPN):
   devices on it open `http://<machine>:8080` after setting `DEMO_BIND_ADDRESS` to the
   machine's VPN address only. Nothing is opened on the router.
3. **A public name** (only if you must): a DNS name pointing at the machine, port 443
   forwarded to it, `DEMO_SERVER_NAME=<that name>` and `DEMO_TLS=<your e-mail>` so Caddy gets
   a public certificate. Keep port 8080 unforwarded, use a long random tester password, and
   prefer an IP allow-list on the router.

If the browser's address differs from what the server sees (an unusual proxy), saving
fails with `origin_not_allowed`: set `EUROGAS_NEXUS_CORS_ORIGINS` to the exact address the
browser shows, for example `https://demo.lan`.

## Security posture

- Without a signed-in session only the sign-in page, the static client files and the health
  probes answer; `/docs` and `/openapi.json` are not mounted; there is no debug endpoint or
  directory listing; an unknown `/api` path is a JSON 404, never the page.
- Session cookies are `HttpOnly`, `SameSite=Lax` and always `Secure` (browsers accept them on
  `http://127.0.0.1` and `http://localhost`; from other devices use HTTPS as above);
  cookie-authenticated writes need the CSRF token and a same-origin `Origin`.
- Responses carry a Content-Security-Policy (scripts from the site only, no framing),
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, and
  HSTS over HTTPS.
- Sign-in is throttled: 30 attempts per minute per client address (behind the HTTPS front
  all devices share the proxy's address, so the limit is effectively server-wide).
- The demo profile refuses to start in a trial or release environment; the demo seed
  refuses to run there.
- Never load real customer data, real trader credentials or licensed market data here.

## Stop, start, update

- Stop: `docker compose stop` (or `down`; data stays in the `eurogas-nexus-demo-postgres`
  volume). Start: `docker compose start` (or `up -d`).
- After a stop of days or weeks the start **rolls the demo desk forward**: the simulated
  flows, storage, LNG, power, month-ahead history, deliveries, FX and outages are extended to
  the current gas day and a new curve snapshot is written. Stored rows and testers' edits are
  not rewritten. Measured on a 30-day gap: 15,342 rows added, ready 24 s after start.
- Update to a new version: `git pull`, then
  `DEMO_GIT_SHA=$(git rev-parse HEAD) docker compose up -d --build`. Migrations run forward on
  start; the demo desk is not re-seeded and testers' work is kept. A failed migration stops
  the start (`alembic upgrade head failed (exit 1)`) and the server does not serve. Going back
  to an older commit after a newer migration ran fails with `Can't locate revision`: restore
  the backup taken before the update.
- Operator tools inside the container: run them through the start script so the database
  URL is mapped the same way, for example
  `docker compose exec demo python scripts/demo/start_public_demo.py run -- python scripts/ops/check_config.py`.

## Back up and restore

```bash
docker compose exec -T postgres pg_dump -U eurogas_demo -Fc eurogas_demo > demo-$(date +%F).dump
# restore into an empty stack:
docker compose up -d postgres
docker compose exec -T postgres pg_restore -U eurogas_demo -d eurogas_demo --clean --if-exists < demo-YYYY-MM-DD.dump
docker compose up -d
```

Keep `.env` with the dump: stored provider keys can only be read with the same
`EUROGAS_NEXUS_SECRET_KEY`. Take a backup before each update.

## Reset the demo data

Set `EUROGAS_NEXUS_DEMO_RESET_TOKEN` in `.env` to a new value (a date is fine) and run
`docker compose up -d`. The start re-seeds the demo desk (rows of the demo books,
contracts and counterparties are replaced, so testers' edits to them are lost) and restores
the tester identities. The same value later does nothing more. Rows testers created
themselves (contracts, scenarios, reviews, users) are kept. For a completely clean store:
`docker compose down -v` (deletes the database volume) and `up -d` again.

What persists: everything in PostgreSQL (testers' work, users, audit, stored provider keys,
ingested public data). What does not: files inside the container (research dataset
artifacts in `/tmp`), in-process sign-in throttling.

## AI and live public data

AI: set `EUROGAS_NEXUS_LLM_API_KEY` (for a model other than DeepSeek also
`EUROGAS_NEXUS_LLM_BASE_URL` and `EUROGAS_NEXUS_LLM_MODEL`) and `docker compose up -d`. The
product's own guards still decide what evidence may leave. Remove the key to turn AI off.

Live data: with a public-source key set (or `EUROGAS_NEXUS_DEMO_LIVE_SOURCES=on`), a
low-priority background process in the demo container waits until the server answers, then
runs a catch-up round and repeats it every 6 hours; it never blocks the health check or
start-up (the server answers about 30 s after a first start). A round reads, with the
commands and read bounds the product's own scheduler uses on a real store
(`scripts/ops/run_dataops_scheduler.py`,
[PRODUCTION_SOURCE_OPERATIONS.md](../operations/PRODUCTION_SOURCE_OPERATIONS.md)):

| Step | Needs | Window of the first round (45-day gap) | Later rounds |
|---|---|---|---|
| Approval of ENTSOG and GIE (see below) | – (GIE: `GIE_API_KEY`) | when no approval is in force | not repeated while in force |
| ECB reference rates | – | the latest fixing | the same |
| ENTSOG reference network, flows and capacity | – | the newest 7 gas days, all points; reference at most daily | the same |
| GIE AGSI storage and ALSI LNG (Europe total and the NW Europe countries) | `GIE_API_KEY` | 45 gas days | at least 30 |
| National Gas GB storage and LNG | – | 30 days | at least 5 |
| National Gas GB demand (D+1, D+6) | – | 31 days | at least 8 |
| Elexon GB power | – | 7 days | at least 2 |
| ENTSO-E power (NL, DE-LU, BE, FR) | `ENTSOE_SECURITY_TOKEN` | 7 days (longer documents time out) | 7 days |
| EIA Henry Hub | `EIA_API_KEY` | 45 days | at least 14 |
| SONIA, €STR, SOFR | – | 45 days | at least 10 |
| GIE REMIT storage and LNG outages (IIP) | `GIE_API_KEY` | 30 days | at least 2 |
| ENTSOG REMIT transmission outages | – | 45 days of publications, plus every running event | at least 7 |
| Simulated series now covered by real data | – | removed (see below) | the same |
| ENTSOG flows of the older weeks | – | the rest of the gap in 7-day windows | only after a pause |

Each step runs in its own process and logs one line; a failed step does not stop the
others. A step that failed (rate limit, reset, provider outage) reads its whole gap again at
the next round, while the others read only theirs. Expected lines (first round):

```
[demo-start] catch-up: reading the gap since each source's last good round (45 day(s))
[demo-start] catch-up ENTSOG approval (no certification record): approved in 7s
[demo-start] catch-up GIE approval (no certification record): approved in 3s
[demo-start] catch-up ECB reference rates: ok in 2s (records 12)
[demo-start] catch-up ENTSOG reference, flows and capacity (7 gas days): ok in 114s (records ...)
[demo-start] catch-up Elexon GB power (7 days): failed (exit 1) in 62s (records 1198, inserted 1198; failures: TimeoutError)
...
[demo-start] catch-up round finished in ...s: 16 sources ok, 1 failed (elexon; retried at the next refresh)
```

Each round is an audit event `demo.catch_up` (`ok=` and `failed=` step lists); a round by
hand: `docker compose exec demo python scripts/demo/start_public_demo.py catch-up`. While a
dataset is behind it shows late or stale on screen; nothing stale is presented as current.

**Approval.** ENTSOG and GIE are read only after an administrator approves them for the
firm (the fail-closed gate in `scripts/ops/ingest_public_sources.py`; without an approval a
read is refused with `source_not_approved`). A customer installation does this on Admin →
Data sources or with `scripts/ops/approve_public_source.py` (see
[DEPLOYMENT_ROLES-EN.md](DEPLOYMENT_ROLES-EN.md), "First run"). The demo runs that same
command at the start of a round, as a demo-profile action. **On the demo, setting a key in
`.env` or `EUROGAS_NEXUS_DEMO_LIVE_SOURCES=on` is the operator's acceptance of the ENTSOG and
GIE terms for that demo; a customer installation never does this and always requires an
administrator's explicit approval.** The
approval is recorded as operator `demo-start` with the reason "demo profile: approved by the
demo start-up because the operator turned live public sources on for this demo", audited by
the product (`source.approval`) and by the demo (`demo.certify`). It runs the product's
bounded live validation and only when no approval is in force. The gate itself is unchanged.
Use only keys and sources whose terms allow this use; the terms summary each approval
records is in [DATA_SOURCE_TERMS.md](../legal/DATA_SOURCE_TERMS.md).

**Real and simulated data.** The demo desk ships simulated flows, storage, LNG, power
fundamentals, FX and two fictional outages so every screen works without keys. Once a real
source has stored a series, the simulated series of the same scope is removed (storage and
LNG by country, power by zone, FX by currency pair; all simulated network flows once ENTSOG
flows are stored; the fictional outages once real REMIT messages are stored), so no screen
mixes the two in one series or adds them up, and later roll-forwards do not bring them back.
What no public source replaces stays simulated and is labelled `sim`: demo prices, the demo
book, its deliveries and curve. Scopes a source did not cover (no key, a failed step) stay
simulated until it does.

Catch-up time, measured on a fresh stack with all three keys (2026-11-16, through a slow
outbound proxy). With the approval step and a week of ENTSO-E: the server answered 32 s
after start and the first round took 13 minutes with all 15 sources ok (approvals 6 s and
10 s; ENTSOG newest week 119 s; GIE 56 s; ENTSO-E 88 s; GIE IIP 222 s; six older ENTSOG
weeks 19–51 s each). An earlier run, before those changes: the first round took 17 minutes
(approval 10 s; ECB 2 s; ENTSOG reference, newest week and capacity 114 s, then six
older weeks of flows 27–70 s each; GIE 9 s; National Gas 4 s; Elexon 62 s; ENTSO-E 409 s for
a month, now read a week at a time, about 4 minutes; EIA, rates 2–4 s each; GIE IIP 94 s;
ENTSOG UMMs 4 s). A later round took about 8 minutes, most of it ENTSO-E and ENTSOG. Stored
by the first round: ENTSOG flows 36,115 rows, capacity 10,465, reference 789 points; GIE
storage 270, LNG 225; National Gas storage 30, LNG 30, demand 169; ENTSO-E power 59,714;
Elexon 1,198; ECB 12; EIA 29; SONIA, €STR, SOFR about 30 each; REMIT messages 550 (GIE IIP)
and 36 (ENTSOG). A restart on the same volume added no duplicate rows. Elexon and ENTSO-E
answered some requests with timeouts in that run; the step logged the failure with the rows
it did store, and the next round read its gap again.

Keys stored through the Credentials screen instead of `.env` are used too, but `auto` cannot
see them: set `EUROGAS_NEXUS_DEMO_LIVE_SOURCES=on`, and for a model key stored there
`EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED=true` (add it to the `environment:` list of the
`demo` service). Use only keys whose terms allow this use.

## A database elsewhere

Set `DEMO_DATABASE_URL` to the provider's URI, for example
`postgres://USER:PASSWORD@HOST:PORT/defaultdb?sslmode=require` (an Aiven-style service).
`postgres://` and `postgresql://` are mapped to the pg8000 driver; non-default ports and
URL-encoded passwords work as given. `sslmode=require` encrypts without checking the
certificate; `verify-full` checks it against `EUROGAS_NEXUS_DB_SSL_ROOT_CERT` (the provider's
CA as PEM text, or a file you mount) or the system trust store; `verify-ca` checks the chain
only. The demo uses at most 12 connections for the server plus 1–3 during start-up steps or
a catch-up round, and closes them on shutdown, which suits plans limited to about 20. The
local `postgres` service still starts; it is simply unused.

## When it does not start

| What you see | Cause | Fix |
|---|---|---|
| `required variable … is missing a value` from Compose, or `[demo-start] FATAL: refusing to start: - EUROGAS_NEXUS_DEV_LOGIN_PASSWORD (the tester password) is unset or shorter than 12 characters` | `.env` missing, not in `deploy/demo/`, or a value too short | Copy `.env.example` to `.env` next to `compose.yaml` and fill the three secrets |
| `[demo-start] FATAL: database not reachable after 90s at postgresql+pg8000://user:***@host…` with `password authentication failed` | `DEMO_DB_PASSWORD` changed after the volume was created (PostgreSQL keeps the first one), or a wrong external URL | Restore the original value, or `docker compose down -v` to start a fresh database (deletes data) |
| `Bind for 127.0.0.1:8080 failed: port is already allocated` (or 443 for the HTTPS front) | Another program uses the port | Set `DEMO_PORT` / `DEMO_HTTPS_PORT` to a free port |
| Cards show "No response within the 10 second read timeout" | Too little CPU for the first workspace load | Retry; give Docker Desktop more CPU (Settings, Resources) |

## Footprint

Measured with the built image on this repository's build machine:

| | Unlimited (4 cores) | 0.5 vCPU / 512 MB | 0.2 vCPU / 512 MB | 0.1 vCPU / 256 MB |
|---|---|---|---|---|
| First start (migrate, seed) to healthy | 35 s | not measured | 119 s | 270 s |
| Start after a 30-day stop | 24 s | — | 88 s | — |
| Start with nothing to do | 19 s | 18 s | 54 s | — |
| Page load after sign-in (full reload) | 6–10 s | 8–12 s | 17–26 s, several cards time out | unusable (sign-in times out) |

Memory: the demo container uses about 100 MiB idle and 165 MiB after a tester walk-through;
the first start peaks at 214 MiB, and a live-data catch-up round adds about 80 MiB while it
runs (peak 243 MiB). PostgreSQL uses 50–65 MiB. Image: 230 MB (53 MB compressed). Database
after seeding: 35–40 MB. A cached rebuild takes about 11 s, a clean one about 40 s on a fast
connection. The first workspace load after sign-in costs about 5 CPU-seconds on the server,
which is why fewer than half a core feels slow.

## Known limits

- Map labels request a font stack the tile service does not have (404 for
  `Open Sans Regular,Arial Unicode MS Regular`); tiles render. Handled separately (a bundled
  basemap replaces the remote one).
- One demo container only: sign-in throttling and the refresh process are per process.
