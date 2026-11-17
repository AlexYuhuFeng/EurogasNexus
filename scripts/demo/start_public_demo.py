#!/usr/bin/env python
"""Start the hosted test/demo server (the root ``Dockerfile`` image). Never a customer runtime.

One container, one port: this prepares the database and then replaces itself with one
uvicorn process that serves the API and the built web client from the same origin.
See ``docs/deployment/SELF_HOSTED_DEMO.md`` for the operator guide.

``serve`` (default), in order, failing loudly at the first problem:

1. read the configuration from the environment and refuse to start without the
   database URL, ``EUROGAS_NEXUS_SECRET_KEY`` or a tester password of 12+ characters;
   a platform URI (``postgres://``/``postgresql://`` with ``sslmode``) is mapped to the
   pg8000 URL the product uses;
2. wait for PostgreSQL (up to ``DEMO_DB_WAIT_SECONDS``, default 90);
3. ``alembic upgrade head`` (forward only; a failure stops this version from serving);
4. load the shipped reference network bundle (idempotent, no network);
5. seed the fictional demo desk once, on an empty store. Later starts keep what testers
   changed, unless ``EUROGAS_NEXUS_DEMO_RESET_TOKEN`` differs from the value recorded at the
   last seed (an audit event ``demo.seed``), which re-seeds the demo rows. A start that does
   not seed rolls the simulated series forward to the current gas day (after a pause),
   appending only what is missing;
6. create the tester identities that do not exist yet (all re-applied on a reset);
7. when live public sources are on (``EUROGAS_NEXUS_DEMO_LIVE_SOURCES``: ``auto`` turns them
   on when a public-source key is set), start a low-priority background process that waits
   until the server answers, catches up the gap since the last successful round (at most
   ``EUROGAS_NEXUS_DEMO_CATCH_UP_MAX_DAYS``, default 45) and then repeats every
   ``EUROGAS_NEXUS_DEMO_REFRESH_HOURS`` (default 6). It never blocks the health check;
8. exec ``uvicorn`` with one worker on ``$PORT`` (default 8080).

``run -- <command>`` runs an operator tool (``docker compose exec demo python
scripts/demo/start_public_demo.py run -- python scripts/ops/...``) with the same database-URL
mapping and defaults as the server.

``catch-up`` runs one such round in the foreground and exits (by hand: ``docker compose
exec demo python scripts/demo/start_public_demo.py catch-up``). A round first performs the
product's public-source approval for ENTSOG and GIE when none is in force
(``scripts/ops/approve_public_source.py`` as the demo actor ``demo-start``,
with the demo reason and an audit event ``demo.certify``), then runs the ingestion commands
the product's scheduler runs on a real store (``catch_up_steps``): ECB, ENTSOG reference,
flows and capacity, GIE storage and LNG, National Gas GB supply and demand, Elexon, ENTSO-E,
EIA, the SONIA/€STR/SOFR fixings and the GIE and ENTSOG REMIT outages, keyed sources only with
their key; then it removes the simulated demo series that real rows now cover
(``seed_demo_desk.py --retire-simulated``). Each step logs one line, a failed step does not
stop the others and reads its own gap again at the next round.

No secret value is ever printed.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[2]
SEED_ACTION = "demo.seed"
CATCH_UP_ACTION = "demo.catch_up"
CERTIFY_ACTION = "demo.certify"
#: The actor recorded on certifications the demo start-up performs (never a person).
DEMO_CERTIFY_ACTOR = "demo-start"
MIN_PASSWORD_LENGTH = 12
PUBLIC_SOURCE_KEYS = ("GIE_API_KEY", "GIE_API_KEY_FILE", "EIA_API_KEY", "ENTSOE_SECURITY_TOKEN")

# The tester identities (one per role and job function, plus one holding them all). They all
# sign in with the one operator-set password; nothing here is a credential.
# (name, display name, primary role, roles, job functions, office)
TESTERS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...], str], ...] = (
    (
        "tester",
        "Tester (all roles)",
        "ADMIN",
        ("ADMIN", "ANALYST", "OPERATOR", "REVIEWER"),
        (
            "TRADER",
            "HQ_BUSINESS_ANALYST",
            "QUANT_RESEARCHER",
            "RISK_MANAGER",
            "REVIEWER_MANAGEMENT",
            "MANAGEMENT",
            "FINANCE_SETTLEMENT",
            "LEGAL_COMPLIANCE",
            "DATA_OPERATOR",
            "PLATFORM_ADMINISTRATOR",
        ),
        "UK",
    ),
    ("demo.trader", "Demo trader (NBP)", "ANALYST", ("ANALYST",), ("TRADER",), "UK"),
    ("demo.nl.trader", "Demo trader (TTF)", "ANALYST", ("ANALYST",), ("TRADER",), "NL"),
    (
        "demo.analyst",
        "Demo analyst / quant",
        "ANALYST",
        ("ANALYST",),
        ("HQ_BUSINESS_ANALYST", "QUANT_RESEARCHER"),
        "UK",
    ),
    ("demo.risk", "Demo risk manager", "REVIEWER", ("REVIEWER",), ("RISK_MANAGER",), "UK"),
    (
        "demo.manager",
        "Demo management",
        "REVIEWER",
        ("REVIEWER",),
        ("MANAGEMENT", "REVIEWER_MANAGEMENT"),
        "UK",
    ),
    ("demo.finance", "Demo finance", "VIEWER", ("VIEWER",), ("FINANCE_SETTLEMENT",), "UK"),
    ("demo.compliance", "Demo compliance", "REVIEWER", ("REVIEWER",), ("LEGAL_COMPLIANCE",), "UK"),
    ("demo.ops", "Demo data operations", "OPERATOR", ("OPERATOR",), ("DATA_OPERATOR",), "UK"),
    (
        "demo.admin",
        "Demo platform administrator",
        "ADMIN",
        ("ADMIN",),
        ("PLATFORM_ADMINISTRATOR",),
        "UK",
    ),
)
TESTER_NAMES = tuple(row[0] for row in TESTERS)


class StartupError(RuntimeError):
    """A start-up step failed; the message is what the operator reads in the log."""


def log(message: str) -> None:
    print(f"[demo-start] {message}", flush=True)


def configure_environment(environ: dict[str, str] | os._Environ) -> list[str]:
    """Validate and complete the process environment for the demo server.

    Returns the names of the settings this function filled in. Raises
    :class:`StartupError` naming every missing or unusable required variable.
    """

    from eurogas_nexus.db.connection_url import DatabaseUrlError, normalize_database_url

    filled: list[str] = []
    problems: list[str] = []

    raw_url = next(
        (
            environ[name].strip()
            for name in ("RUNTIME_STORE_DATABASE_URL", "DATABASE_URL", "POSTGRES_URI")
            if (environ.get(name) or "").strip()
        ),
        "",
    )
    if not raw_url:
        problems.append(
            "DATABASE_URL (or POSTGRES_URI) is not set: set it to the PostgreSQL "
            "connection URI"
        )
    else:
        try:
            environ["RUNTIME_STORE_DATABASE_URL"] = normalize_database_url(raw_url)
        except DatabaseUrlError as exc:
            problems.append(f"the database URL is unusable: {exc}")

    if not (environ.get("EUROGAS_NEXUS_SECRET_KEY") or "").strip():
        problems.append(
            "EUROGAS_NEXUS_SECRET_KEY is not set: generate one with "
            "python -c \"import base64,os;"
            "print(base64.urlsafe_b64encode(os.urandom(32)).decode())\""
            " and keep it stable (stored provider keys are encrypted with it)"
        )
    password = (environ.get("EUROGAS_NEXUS_DEV_LOGIN_PASSWORD") or "").strip()
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(
            "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD (the tester password) is unset or shorter than "
            f"{MIN_PASSWORD_LENGTH} characters: set a random one as a secret"
        )

    environment = (environ.get("EUROGAS_NEXUS_ENV") or "development").strip().lower()
    if environment not in {"development", "test"}:
        problems.append(
            f"EUROGAS_NEXUS_ENV={environment!r}: the demo image runs only as development "
            "(simulated demo data is refused in trial and release)"
        )
    profile = (environ.get("EUROGAS_NEXUS_API_PROFILE") or "demo").strip().lower()
    if profile != "demo":
        problems.append(
            f"EUROGAS_NEXUS_API_PROFILE={profile!r}: the demo image serves the demo profile only"
        )
    if problems:
        raise StartupError("refusing to start:\n  - " + "\n  - ".join(problems))

    llm_key = any(
        (environ.get(name) or "").strip()
        for name in ("EUROGAS_NEXUS_LLM_API_KEY", "DEEPSEEK_API_KEY")
    )
    defaults = {
        "EUROGAS_NEXUS_ENV": "development",
        "EUROGAS_NEXUS_API_PROFILE": "demo",
        "EUROGAS_NEXUS_DEV_LOGIN_USERNAME": ",".join(TESTER_NAMES),
        # Demo prices value the demo book; every valued response says they are demo prices.
        "EUROGAS_NEXUS_DEMO_MARKS": "true",
        # AI only when the operator supplied a model key.
        "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "true" if llm_key else "false",
        "EUROGAS_NEXUS_WEB_CLIENT_DIR": str(ROOT / "web"),
        "EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT": "/tmp/eurogas-nexus-snapshots",
        # Small managed PostgreSQL plans allow a handful of connections.
        "EUROGAS_NEXUS_DB_POOL_SIZE": "3",
        "EUROGAS_NEXUS_DB_MAX_OVERFLOW": "2",
    }
    for name, value in defaults.items():
        if not (environ.get(name) or "").strip():
            environ[name] = value
            filled.append(name)
    if not (environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN") or "").strip():
        # The deployment-token path (SDK/CLI) stays closed: a random value no one knows,
        # regenerated at every start and never printed. Browsers sign in instead.
        environ["EUROGAS_NEXUS_PUBLIC_API_TOKEN"] = secrets.token_urlsafe(32)
        filled.append("EUROGAS_NEXUS_PUBLIC_API_TOKEN (random, not shown)")
    return filled


def wait_for_database(timeout_seconds: float) -> None:
    from sqlalchemy import text

    from eurogas_nexus.db.session import get_engine, redact_database_url, resolve_database_url

    url = resolve_database_url()
    engine = get_engine(url, pool_size=1, max_overflow=0)
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    try:
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                log(f"database reachable at {redact_database_url(url)}")
                return
            except Exception as exc:  # noqa: BLE001 - reported, then retried
                last_error = f"{exc.__class__.__name__}: {str(exc).splitlines()[0][:200]}"
                if time.monotonic() >= deadline:
                    raise StartupError(
                        f"database not reachable after {timeout_seconds:.0f}s at "
                        f"{redact_database_url(url)} ({last_error})"
                    ) from exc
                time.sleep(2)
    finally:
        engine.dispose()


def run_step(name: str, command: list[str]) -> None:
    """Run one start-up step in its own process, so its memory is returned before serving."""

    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, check=False)
    elapsed = time.monotonic() - started
    if result.returncode != 0:
        raise StartupError(f"{name} failed (exit {result.returncode}); see the lines above")
    log(f"{name} done in {elapsed:.1f}s")


def last_seed_token(session) -> str | None:
    """Return the reset token recorded at the last demo seed, or ``None`` if never seeded."""

    from eurogas_nexus.db.models import TradingBookRecord
    from eurogas_nexus.db.models.observation import AuditEventRecord

    row = (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.action == SEED_ACTION)
        .order_by(AuditEventRecord.event_ts_utc.desc())
        .first()
    )
    if row is not None:
        return row.detail.partition("reset_token=")[2]
    # Seeded before this script recorded its marker (e.g. by hand): treat as seeded.
    if session.get(TradingBookRecord, "demo-uk-nbp") is not None:
        return ""
    return None


def record_seed(session, token: str, reason: str) -> None:
    from eurogas_nexus.db.models.observation import AuditEventRecord

    session.add(
        AuditEventRecord(
            event_id=f"demo-seed-{secrets.token_hex(8)}",
            event_type="governance.demo",
            severity="info",
            principal="demo-seed",
            action=SEED_ACTION,
            resource="demo_desk",
            outcome="success",
            detail=f"reason={reason}; reset_token={token}",
            event_ts_utc=datetime.now(UTC),
            source_system="demo-start",
            human_review_required=False,
        )
    )


def ensure_testers(session, *, reapply: bool) -> tuple[int, int]:
    """Create missing tester identities; on a reset, restore every tester's definition."""

    from eurogas_nexus.db.models import IdentityPrincipalRecord
    from eurogas_nexus.db.repositories.identity import create_identity_principal

    created = restored = 0
    now = datetime.now(UTC)
    for name, display, role, roles, functions, office in TESTERS:
        row = (
            session.query(IdentityPrincipalRecord)
            .filter(IdentityPrincipalRecord.name == name)
            .one_or_none()
        )
        if row is None:
            row = create_identity_principal(
                session, name=name, display_name=display, role=role, data_scopes=["*"], now_utc=now
            )
            created += 1
        elif reapply:
            restored += 1
        else:
            continue
        row.display_name = display
        row.role = role
        row.roles = list(roles)
        row.job_functions = list(functions)
        row.office = office
        row.status = "ACTIVE"
        row.data_scopes = ["*"]
        row.updated_at_utc = now
    session.flush()
    return created, restored


def prepare_database() -> None:
    from eurogas_nexus.db.session import get_session_factory

    python = sys.executable
    run_step("alembic upgrade head", [python, "-m", "alembic", "upgrade", "head"])
    run_step(
        "reference network bundle",
        [python, "scripts/ops/seed_reference_network.py"],
    )

    token = (os.environ.get("EUROGAS_NEXUS_DEMO_RESET_TOKEN") or "").strip()
    factory = get_session_factory()
    with factory() as session:
        previous = last_seed_token(session)
    if previous is None:
        reason = "empty store"
    elif token and token != previous:
        reason = "reset token changed"
    else:
        reason = ""
    if reason:
        log(f"seeding the demo desk ({reason})")
        run_step("demo desk seed", [python, "scripts/demo/seed_demo_desk.py"])
    else:
        log("demo desk already seeded; testers' changes kept (change "
            "EUROGAS_NEXUS_DEMO_RESET_TOKEN to re-seed)")
        run_step(
            "demo series roll-forward",
            [python, "scripts/demo/seed_demo_desk.py", "--roll-forward"],
        )
    with factory() as session:
        created, restored = ensure_testers(session, reapply=bool(reason))
        if reason:
            record_seed(session, token, reason)
        session.commit()
    log(
        f"tester identities: {created} created, {restored} restored, "
        f"{len(TESTERS) - created - restored} kept ({', '.join(TESTER_NAMES)})"
    )


def live_sources_enabled() -> bool:
    """``on``/``off`` as set; ``auto`` (default) is on when a public-source key is present."""

    setting = (os.environ.get("EUROGAS_NEXUS_DEMO_LIVE_SOURCES") or "auto").strip().lower()
    if setting in {"on", "true", "1", "yes"}:
        return True
    if setting in {"off", "false", "0", "no"}:
        return False
    return any((os.environ.get(name) or "").strip() for name in PUBLIC_SOURCE_KEYS)


def _int_setting(name: str, default: int, *, low: int, high: int) -> int:
    try:
        value = int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        value = default
    return max(low, min(high, value))


def start_background_refresh() -> None:
    """Spawn the live-source refresher; it outlives this process image (exec keeps the PID)."""

    subprocess.Popen(  # noqa: S603 - fixed command, this interpreter and this script
        [sys.executable, str(Path(__file__).resolve()), "refresh-loop"],
        cwd=ROOT,
        start_new_session=True,
    )
    log("live public sources on: catch-up starts in the background once the server answers")


def serve() -> int:
    started = time.monotonic()
    filled = configure_environment(os.environ)
    if filled:
        log("defaults applied: " + ", ".join(filled))
    wait_for_database(float(os.environ.get("DEMO_DB_WAIT_SECONDS") or 90))
    prepare_database()
    port = (os.environ.get("PORT") or "8080").strip()
    if live_sources_enabled():
        start_background_refresh()
    else:
        log("live public sources off (no public-source key set); demo data only")
    log(f"start-up steps finished in {time.monotonic() - started:.1f}s; serving on port {port}")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "apps.api.main:app",
        "--host",
        "0.0.0.0",
        "--port",
        port,
        "--workers",
        "1",
        "--no-server-header",
    ]
    os.chdir(ROOT)
    os.execv(sys.executable, command)
    return 0  # pragma: no cover - execv does not return


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _succeeded_keys(detail: str) -> set[str]:
    """Step keys a round's audit detail lists as succeeded (``ok=ecb,entsog``)."""

    match = re.search(r"(?:^|; )ok=([^;]*)", detail or "")
    return {key for key in (match.group(1).split(",") if match else ()) if key}


def catch_up_window_days(session, now: datetime, max_days: int, key: str | None = None) -> int:
    """Days to read: since the last successful round, at least 1, at most ``max_days``.

    With ``key``, a round counts as successful for that step when the step succeeded in it,
    so a step that failed for an upstream reason (rate limit, reset, outage) reads its whole
    gap again at the next refresh while the steps that worked read only theirs.
    """

    from eurogas_nexus.db.models.observation import AuditEventRecord

    query = (
        session.query(AuditEventRecord)
        .filter(AuditEventRecord.action == CATCH_UP_ACTION)
        .order_by(AuditEventRecord.event_ts_utc.desc())
    )
    last = None
    for row in query.limit(500):
        if row.outcome == "success" or (key is not None and key in _succeeded_keys(row.detail)):
            last = _aware(row.event_ts_utc)
            break
    if last is None:
        return max_days
    gap = (now - last) / timedelta(days=1)
    return max(1, min(max_days, int(gap) + 1))


class CatchUpStep(NamedTuple):
    """One ingestion command of a round: ``key`` tracks its own last success."""

    key: str
    name: str
    command: list[str]


#: Per-step reading window in days: (at least, at most). The lower bound is the window the
#: product's own scheduler reads for that source (``scripts/ops/run_dataops_scheduler.py``,
#: docs/operations/PRODUCTION_SOURCE_OPERATIONS.md), so a 6-hourly demo round re-reads the
#: same revisions the scheduler would; the upper bound is the script's own limit or what a
#: round can read in a few minutes.
STEP_WINDOWS: dict[str, tuple[int, int]] = {
    "gie": (30, 365),  # newest N gas days per product and country (--limit)
    "national-gas-supply": (5, 30),  # script limit 1..30
    "national-gas-demand": (8, 31),  # provider window limit 31
    "elexon": (2, 7),  # three requests a settlement day
    # Four zones, three documents, one request each: a month-long document timed out (30 s
    # read timeout) through a slow link, a week took about 4 minutes in all.
    "entsoe": (7, 7),
    "eia": (14, 365),
    "rates": (10, 365),
    "remit-iip": (2, 30),  # page bound: about one page of 50 per day
    "entsog-umm": (7, 365),  # the whole dataset is read; the window selects publications
}
#: ENTSOG reads in windows of at most a week, the scheduler's measured complete read
#: (flows about 6,800 records, capacity about 12,200, within the transport's 50 x 1,000).
#: The newest week carries flows, capacity and the reference refresh (at most daily);
#: older weeks of a catch-up carry flows only.
ENTSOG_WEEK = 7
ENTSOG_BOUNDS = (
    "--limit", "50000", "--entsog-page-size", "1000", "--entsog-max-pages", "50",
)


def _window(key: str, days: int) -> int:
    low, high = STEP_WINDOWS[key]
    return max(low, min(high, days))


def _has(environ, *names: str) -> bool:
    return any((environ.get(name) or "").strip() for name in names)


def catch_up_steps(
    days: int, now: datetime, environ=os.environ, windows: dict[str, int] | None = None
) -> list[CatchUpStep]:
    """The ingestion commands of one round, each through the source's own window option.

    ``days`` is the round's gap; ``windows`` may give a step key its own gap (a step that
    failed last round). Keyed sources run only with their key. The commands and read bounds
    are the ones the product's scheduler runs on a real store.
    """

    python = sys.executable
    ingest = [python, "scripts/ops/ingest_public_sources.py", "--json"]

    def gap(key: str) -> int:
        return (windows or {}).get(key, days)

    def script(name: str, *args: str) -> list[str]:
        return [python, f"scripts/ops/{name}", *args]

    anchor = now.replace(microsecond=0).isoformat()
    steps = [
        CatchUpStep("ecb", "ECB reference rates", [*ingest, "--source", "ecb"]),
        CatchUpStep(
            "entsog",
            f"ENTSOG reference, flows and capacity ({ENTSOG_WEEK} gas days)",
            [*ingest, *ENTSOG_BOUNDS, "--source", "entsog-reference", "--source", "entsog",
             "--source", "entsog-capacity", "--entsog-reference-max-age-hours", "24",
             "--entsog-lookback-gas-days", str(ENTSOG_WEEK), "--entsog-window-anchor", anchor],
        ),
    ]
    if _has(environ, "GIE_API_KEY", "GIE_API_KEY_FILE"):
        limit = _window("gie", gap("gie"))
        steps.append(CatchUpStep(
            "gie", f"GIE AGSI storage and ALSI LNG ({limit} gas days)",
            [*ingest, "--source", "gie-agsi", "--source", "gie-alsi", "--limit", str(limit),
             "--gie-country", "nwe"],
        ))
    for key, name, command in (
        ("national-gas-supply", "National Gas GB storage and LNG",
         ("ingest_national_gas_supply.py", "--commit", "--json")),
        ("national-gas-demand", "National Gas GB demand",
         ("ingest_national_gas_demand.py", "--json")),
        ("elexon", "Elexon GB power", ("ingest_power_gb.py", "--commit", "--json")),
    ):
        window = _window(key, gap(key))
        steps.append(CatchUpStep(key, f"{name} ({window} days)",
                                 script(*command, "--days", str(window))))
    if _has(environ, "ENTSOE_SECURITY_TOKEN"):
        window = _window("entsoe", gap("entsoe"))
        steps.append(CatchUpStep("entsoe", f"ENTSO-E power ({window} days)",
                                 script("ingest_power.py", "--commit", "--json",
                                        "--days", str(window))))
    if _has(environ, "EIA_API_KEY"):
        window = _window("eia", gap("eia"))
        steps.append(CatchUpStep("eia", f"EIA Henry Hub ({window} days)",
                                 script("ingest_eia.py", "--json", "--days", str(window))))
    for benchmark in ("SONIA", "ESTR", "SOFR"):
        key = f"rates-{benchmark.lower()}"
        window = _window("rates", gap(key))
        steps.append(CatchUpStep(
            key, f"{benchmark} benchmark rate ({window} days)",
            script("ingest_interest_rates.py", "--json", "--benchmark", benchmark,
                   "--days", str(window)),
        ))
    if _has(environ, "GIE_API_KEY", "GIE_API_KEY_FILE"):
        window = _window("remit-iip", gap("remit-iip"))
        steps.append(CatchUpStep("remit-iip", f"GIE REMIT storage and LNG outages ({window} days)",
                                 script("ingest_remit_iip.py", "--commit", "--json",
                                        "--days", str(window))))
    window = _window("entsog-umm", gap("entsog-umm"))
    steps.append(CatchUpStep("entsog-umm", f"ENTSOG REMIT transmission outages ({window} days)",
                             script("ingest_remit_entsog.py", "--commit", "--json",
                                    "--days", str(window))))
    # The simulated fundamentals a real source now covers go, so no series mixes the two.
    steps.append(CatchUpStep(
        "replace-simulated", "simulated series now covered by real data (rows removed)",
        [python, "scripts/demo/seed_demo_desk.py", "--retire-simulated"],
    ))
    # Older ENTSOG weeks last: the longest reads, and the pages above do not wait for them.
    history = gap("entsog-history")
    if history > ENTSOG_WEEK:
        current = now.astimezone(UTC).date()
        end = current - timedelta(days=ENTSOG_WEEK)
        first = current - timedelta(days=history)
        while end > first:
            start = max(first, end - timedelta(days=ENTSOG_WEEK))
            steps.append(CatchUpStep(
                "entsog-history", f"ENTSOG flows {start.isoformat()} to {end.isoformat()}",
                [*ingest, *ENTSOG_BOUNDS, "--source", "entsog",
                 "--entsog-from", start.isoformat(), "--entsog-to", end.isoformat()],
            ))
            end = start
    return steps


def _report_summary(stdout: str) -> tuple[bool | None, str]:
    """``(ok, one-line counts)`` from a step's JSON report (the scheduler's report shape)."""

    # The whole output (an indented report), else the last line that is a JSON object (a
    # one-line report after progress lines).
    candidates = [(stdout or "").strip(), *reversed((stdout or "").strip().splitlines())]
    report = None
    for text in candidates:
        try:
            value = json.loads(text)
        except ValueError:
            continue
        if isinstance(value, dict):
            report = value
            break
    if report is None:
        return None, ""
    sources = report.get("sources") if isinstance(report.get("sources"), dict) else {}
    totals = {"records": 0, "inserted": 0, "updated": 0, "revised": 0}
    notes = []
    for name, detail in sources.items():
        if not isinstance(detail, dict):
            continue
        for field in totals:
            value = detail.get(field)
            if isinstance(value, int) and not isinstance(value, bool):
                totals[field] += value
        if detail.get("status") == "skipped_fresh":
            notes.append(f"{name} fresh, not re-read")
    codes = sorted({
        str(failure.get("code"))
        for failure in report.get("failures") or []
        if isinstance(failure, dict) and failure.get("code")
    })
    text = ", ".join(f"{field} {value}" for field, value in totals.items() if value or
                     field == "records")
    if notes:
        text += "; " + "; ".join(notes)
    if codes:
        text += "; failures: " + ",".join(codes)
    return report.get("ok") is not False and not codes, text


def run_catch_up_step(step: CatchUpStep) -> bool:
    """Run one step in its own process and log one line: what it stored, or why it failed."""

    started = time.monotonic()
    result = subprocess.run(step.command, cwd=ROOT, check=False, capture_output=True, text=True)
    elapsed = time.monotonic() - started
    ok, summary = _report_summary(result.stdout)
    succeeded = result.returncode == 0 and ok is not False
    if succeeded:
        log(f"catch-up {step.name}: ok in {elapsed:.0f}s ({summary or 'no report'})")
    else:
        # The counts, and the first reason the step itself printed (never a secret: the
        # ingest scripts report references, not URLs with keys).
        reasons = [
            line.strip() for line in (result.stderr or "").splitlines()
            if "Error" in line or "error" in line
        ]
        tail = (reasons or (result.stderr or "").strip().splitlines()[-1:] or [""])[0][:200]
        why = "; ".join(part for part in (summary, tail) if part) or "no output"
        log(f"catch-up {step.name}: failed (exit {result.returncode}) in {elapsed:.0f}s ({why})")
    return succeeded


#: Certification-gated public sources: (system, certify --source, credential variables).
CERTIFIED_SOURCES = (("ENTSOG", "entsog", ()), ("GIE", "gie", ("GIE_API_KEY", "GIE_API_KEY_FILE")))
#: Renew a demo certification this long before it expires (the record is valid 90 days).
CERTIFICATION_RENEW_DAYS = 7
CERTIFICATION_REASON = (
    "demo profile: approved by the demo start-up because the operator turned live public "
    "sources on for this demo (EUROGAS_NEXUS_API_PROFILE=demo)"
)


def certification_due(session, system: str, now: datetime) -> str | None:
    """Why ``system`` needs a (re)certification now, or ``None`` when its record is current."""

    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate

    record = latest_certification(session, system)
    if record is None:
        return "no certification record"
    gate = certification_gate(system, stage=record.get("stage", ""), checks=record.get("checks"))
    if not gate.allows_live:
        return f"gate {gate.reason}"
    expires = record.get("expires_at_utc")
    if expires and _aware(datetime.fromisoformat(expires)) - now < timedelta(
        days=CERTIFICATION_RENEW_DAYS
    ):
        return f"expires {expires[:10]}"
    return None


def certify_public_sources(factory, now: datetime, environ=os.environ) -> None:
    """The product's public-source approval, run as a demo-profile action.

    ENTSOG and GIE are read only after an administrator approved them (the fail-closed
    ingestion gate). A customer administrator approves on Admin -> Connectors or with
    ``scripts/ops/approve_public_source.py``; the demo runs that same command at start-up,
    because the operator who turned live sources on for the demo (a key in ``.env`` or
    ``EUROGAS_NEXUS_DEMO_LIVE_SOURCES=on``) asked for them. It is recorded as the demo actor
    ``demo-start`` with the demo reason, audited (``source.approval`` from the product and
    ``demo.certify`` from the demo), and runs the same bounded live validation. The gate is
    not changed, and nothing here is in the customer image.
    """

    from eurogas_nexus.db.models.observation import AuditEventRecord

    for system, source, keys in CERTIFIED_SOURCES:
        if keys and not _has(environ, *keys):
            continue
        with factory() as session:
            reason = certification_due(session, system, now)
        if reason is None:
            log(f"catch-up {system} approval: in force, not repeated")
            continue
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, "scripts/ops/approve_public_source.py", "--source", source,
             "--operator", DEMO_CERTIFY_ACTOR, "--reason", CERTIFICATION_REASON,
             "--accept-terms", "--json"],
            cwd=ROOT, check=False, capture_output=True, text=True,
        )
        try:
            state = (json.loads(result.stdout).get("results") or [{}])[0].get("state", "unknown")
        except (ValueError, AttributeError):
            state = "not recorded"
        outcome = "success" if result.returncode == 0 else "failed"
        log(
            f"catch-up {system} approval ({reason}): {state} in "
            f"{time.monotonic() - started:.0f}s"
            + ("" if result.returncode == 0 else
               f" ({((result.stderr or '').strip().splitlines() or [''])[-1][:200]})")
        )
        with factory() as session:
            session.add(
                AuditEventRecord(
                    event_id=f"demo-certify-{secrets.token_hex(8)}",
                    event_type="governance.demo",
                    severity="info" if outcome == "success" else "warning",
                    principal=DEMO_CERTIFY_ACTOR,
                    action=CERTIFY_ACTION,
                    resource=f"provider_certification:{system}",
                    outcome=outcome,
                    detail=f"source={system}; state={state}; due={reason}; "
                           f"reason={CERTIFICATION_REASON}",
                    event_ts_utc=datetime.now(UTC),
                    source_system="demo-start",
                    human_review_required=False,
                )
            )
            session.commit()


def catch_up() -> int:
    """One round of public-source ingestion over the gap since the last successful round."""

    from eurogas_nexus.db.session import get_session_factory

    configure_environment(os.environ)
    wait_for_database(float(os.environ.get("DEMO_DB_WAIT_SECONDS") or 90))
    started = time.monotonic()
    now = datetime.now(UTC)
    max_days = _int_setting("EUROGAS_NEXUS_DEMO_CATCH_UP_MAX_DAYS", 45, low=1, high=365)
    factory = get_session_factory()
    with factory() as session:
        keys = {step.key for step in catch_up_steps(max_days, now)}
        windows = {key: catch_up_window_days(session, now, max_days, key) for key in keys}
    # Each step reads the gap since its own last success (a failed step reads its whole gap).
    days = max(windows.values())
    shortest = min(windows.values())
    log(f"catch-up: reading the gap since each source's last good round "
        f"({shortest if shortest == days else f'{shortest} to {days}'} day(s))")
    certify_public_sources(factory, now)
    ok: list[str] = []
    failed: list[str] = []
    for step in catch_up_steps(days, now, windows=windows):
        (ok if run_catch_up_step(step) else failed).append(step.key)
    succeeded = sorted(set(ok) - set(failed))
    failed_keys = sorted(set(failed))
    with factory() as session:
        from eurogas_nexus.db.models.observation import AuditEventRecord

        session.add(
            AuditEventRecord(
                event_id=f"demo-catch-up-{secrets.token_hex(8)}",
                event_type="governance.demo",
                severity="warning" if failed_keys else "info",
                principal="demo-refresh",
                action=CATCH_UP_ACTION,
                resource="public_sources",
                outcome="partial" if failed_keys else "success",
                detail=f"days={days}; ok={','.join(succeeded)}; "
                       f"failed={','.join(failed_keys) or 'none'}",
                event_ts_utc=now,
                source_system="demo-start",
                human_review_required=False,
            )
        )
        session.commit()
    log(f"catch-up round finished in {time.monotonic() - started:.0f}s: "
        f"{len(succeeded)} sources ok, {len(failed_keys)} failed"
        + (f" ({', '.join(failed_keys)}; retried at the next refresh)" if failed_keys else ""))
    return 1 if failed_keys else 0


def refresh_loop() -> int:
    """Background: wait for the server, then catch up and repeat at the refresh interval."""

    try:
        os.nice(10)  # the API keeps the CPU first on a small instance
    except OSError:
        pass
    port = (os.environ.get("PORT") or "8080").strip()
    deadline = time.monotonic() + 900
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(  # noqa: S310 - loopback health probe
                f"http://127.0.0.1:{port}/api/health/live", timeout=3
            ):
                break
        except OSError:
            time.sleep(5)
    hours = _int_setting("EUROGAS_NEXUS_DEMO_REFRESH_HOURS", 6, low=1, high=168)
    while True:
        result = subprocess.run(  # noqa: S603 - fixed command
            [sys.executable, str(Path(__file__).resolve()), "catch-up"], cwd=ROOT, check=False
        )
        log(f"next catch-up round in {hours}h (exit {result.returncode})")
        time.sleep(hours * 3600)


def run_command(command: list[str]) -> int:
    """Run an operator tool with the demo's resolved configuration (``run -- <command>``).

    ``docker compose exec`` starts a fresh process that never went through ``serve``, so a
    platform URI (``postgres://...?sslmode=...``) in its environment would not be mapped to
    the driver URL. This applies the same mapping and defaults, then becomes the command.
    """

    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        raise StartupError("run needs a command, e.g. run -- python scripts/ops/check_config.py")
    configure_environment(os.environ)
    os.chdir(ROOT)
    os.execvp(command[0], command)
    return 0  # pragma: no cover - execvp does not return


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else "serve"
    try:
        if mode == "run":
            return run_command(argv[2:])
        if mode == "serve":
            return serve()
        if mode == "catch-up":
            return catch_up()
        if mode == "refresh-loop":
            return refresh_loop()
    except StartupError as exc:
        log(f"FATAL: {exc}")
        return 1
    log(f"unknown mode {mode!r}; expected serve, catch-up or run -- <command>")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
