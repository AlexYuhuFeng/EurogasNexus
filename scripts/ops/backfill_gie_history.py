"""Backfill GIE AGSI/ALSI history, one gas year per read, resumably and at a polite pace.

The storage read compares today with the last five complete gas years
(``application/fundamentals_storage.py``), so each country needs about six years of daily
rows. This driver gets them through the **existing** ingestion path, one bounded window per
call of ``scripts/ops/ingest_public_sources.py`` (``--gie-from``/``--gie-to``), so every rule
of that path applies unchanged: the administrator's approval and the certification gate, the
operator's source switch, the key resolution (``GIE_API_KEY``, the key file or the Credentials
screen; never printed), raw-page archiving and the revision rules of
``docs/operations/DATA_REVISIONS.md`` (a later different value is kept as a revision; an
unchanged re-read changes nothing).

Resumable: before each window the store is asked how many gas days of that series it already
holds; a complete window is skipped, so a run stopped by its budget, a refusal or a restart
continues where it left off when started again.

Paced: one window at a time, ``--pace-seconds`` apart (default 2 s; a window is one or two
provider pages, so the default stays below 60 requests a minute; GIE publishes no rate limit).
A rate-limit refusal stops the run (``gie_rate_limited``); the next run resumes.

Bounded: ``--max-windows`` per run (default 60). Incremental mode (``--incremental``) reads,
per series, from a week before its newest stored gas day to yesterday (the week re-reads the
provider's revisions), which is what a scheduler runs daily.

Usage (database URL in ``RUNTIME_STORE_DATABASE_URL``):

    python scripts/ops/backfill_gie_history.py --dry-run           # the plan and coverage
    python scripts/ops/backfill_gie_history.py --years 5 --json     # backfill AGSI
    python scripts/ops/backfill_gie_history.py --product alsi       # LNG by country
    python scripts/ops/backfill_gie_history.py --incremental        # scheduler-friendly
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST = ROOT / "scripts" / "ops" / "ingest_public_sources.py"
#: GIE's largest page; a window of one gas year is two pages.
PAGE = 300
#: Days re-read before the newest stored day in incremental mode (provider revisions).
REVISION_DAYS = 7
#: The EU total is stored under GIE's own code.
TOTAL = "eu"
#: ALSI publishes LNG by these countries (checked live on 2026-11-18; MT, EE, LV, SE, DK, CY
#: and IE answer with no data).
ALSI_COUNTRIES = ("BE", "DE", "ES", "FR", "GR", "HR", "IT", "LT", "NL", "PL", "PT", "FI")


@dataclass(frozen=True)
class Window:
    product: str
    series: str
    first: date
    last: date

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1


def _ingest_module():
    spec = importlib.util.spec_from_file_location("ingest_public_sources", INGEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def series_for(product: str, countries: list[str] | None) -> list[str]:
    """The series of one product: the EU total first, then each country GIE publishes."""

    from eurogas_nexus.application.fundamentals_storage import EU_STORAGE_COUNTRIES

    unpublished = _ingest_module().GIE_UNPUBLISHED_COUNTRIES[product.upper()]
    default = list(EU_STORAGE_COUNTRIES) if product == "agsi" else list(ALSI_COUNTRIES)
    chosen = [c.upper() for c in countries] if countries else default
    return [TOTAL, *[c for c in chosen if c != "EU" and c not in unpublished]]


def gas_year_windows(product: str, series: str, years: int, today: date) -> list[Window]:
    """``years`` complete gas years plus the current one, one window each, oldest first."""

    current = today.year if today.month >= 10 else today.year - 1
    yesterday = today - timedelta(days=1)
    windows = []
    for first_year in range(current - years, current + 1):
        first = date(first_year, 10, 1)
        last = min(date(first_year + 1, 9, 30), yesterday)
        if first <= last:
            windows.append(Window(product, series, first, last))
    return windows


def _model(product: str):
    from eurogas_nexus.db.models.observation import (
        LngObservationRecord,
        StorageObservationRecord,
    )

    return StorageObservationRecord if product == "agsi" else LngObservationRecord


def _day_of(start: datetime) -> date:
    start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
    return (start + timedelta(hours=7)).date()


def held_days(session, window: Window) -> int:
    """Distinct gas days of the window the store holds from GIE for the series."""

    model = _model(window.product)
    first = datetime.combine(window.first, datetime.min.time(), tzinfo=UTC) - timedelta(hours=8)
    last = datetime.combine(window.last, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8)
    naive = session.get_bind().dialect.name == "sqlite"
    rows = (
        session.query(model.period_start_utc)
        .filter(model.source_system == "GIE", model.country == window.series)
        .filter(model.period_start_utc >= (first.replace(tzinfo=None) if naive else first))
        .filter(model.period_start_utc <= (last.replace(tzinfo=None) if naive else last))
        .all()
    )
    return len({d for (start,) in rows if window.first <= (d := _day_of(start)) <= window.last})


def newest_day(session, product: str, series: str) -> date | None:
    from sqlalchemy import func

    model = _model(product)
    value = (
        session.query(func.max(model.period_start_utc))
        .filter(model.source_system == "GIE", model.country == series)
        .scalar()
    )
    return _day_of(value) if value is not None else None


def ingest_command(window: Window) -> list[str]:
    """The ingestion call for one window (the existing path with its gates)."""

    command = [
        sys.executable, str(INGEST),
        "--source", f"gie-{window.product}",
        "--gie-from", window.first.isoformat(),
        "--gie-to", window.last.isoformat(),
        "--limit", str(max(PAGE, math.ceil(window.days / PAGE) * PAGE)),
        "--json",
    ]
    if window.series != TOTAL:
        command += ["--gie-country", window.series, "--gie-skip-total"]
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--product", choices=("agsi", "alsi"), action="append")
    parser.add_argument("--country", action="append", help="Country code (repeatable).")
    parser.add_argument("--years", type=int, default=5, help="Complete prior gas years.")
    parser.add_argument("--incremental", action="store_true")
    parser.add_argument("--max-windows", type=int, default=60)
    parser.add_argument("--pace-seconds", type=float, default=2.0)
    parser.add_argument("--dry-run", action="store_true", help="Plan and coverage only.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--today", type=date.fromisoformat, default=None, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    from sqlalchemy.orm import Session

    from eurogas_nexus.db.session import get_engine, resolve_database_url

    url = resolve_database_url()
    if not url:
        print("RUNTIME_STORE_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    today = args.today or datetime.now(UTC).date()
    engine = get_engine(url)
    plan: list[Window] = []
    with Session(engine) as session:
        for product in args.product or ["agsi"]:
            for series in series_for(product, args.country):
                if args.incremental:
                    newest = newest_day(session, product, series)
                    first = (newest - timedelta(days=REVISION_DAYS)) if newest else (
                        today - timedelta(days=30))
                    window = Window(product, series, first, today - timedelta(days=1))
                    if window.first <= window.last:
                        plan.append(window)
                    continue
                for window in gas_year_windows(product, series, args.years, today):
                    # A complete window is skipped: the run resumes where it stopped.
                    if held_days(session, window) < window.days:
                        plan.append(window)

    report: dict = {"planned": len(plan), "done": [], "empty": [], "failed": [],
                    "remaining": [], "stopped": None}
    if args.dry_run:
        report["remaining"] = [f"{w.product}:{w.series}:{w.first}..{w.last}" for w in plan]
        print(json.dumps(report, indent=2) if args.json else f"{len(plan)} windows to read")
        return 0
    for position, window in enumerate(plan):
        label = f"{window.product}:{window.series}:{window.first}..{window.last}"
        if position >= args.max_windows:
            report["remaining"].append(label)
            continue
        if report["stopped"]:
            report["remaining"].append(label)
            continue
        if position:
            time.sleep(max(0.0, args.pace_seconds))
        completed = subprocess.run(  # noqa: S603 - our own script, fixed arguments
            ingest_command(window), capture_output=True, text=True, cwd=ROOT, check=False
        )
        try:
            outcome = json.loads(completed.stdout or "{}")
        except ValueError:
            outcome = {"ok": False, "failures": [{"code": "unreadable_report"}]}
        codes = sorted({str(f.get("code")) for f in outcome.get("failures") or []})
        records = sum(int(v.get("records") or 0) for v in (outcome.get("sources") or {}).values()
                      if isinstance(v, dict))
        if completed.returncode == 0 and not codes:
            report["done"].append({"window": label, "records": records})
        elif codes == ["gie_no_published_values"]:
            # GIE publishes nothing for the window (an LNG terminal not yet operating): an
            # answer, not a failure. Nothing is stored; a later run asks again.
            report["empty"].append({"window": label})
        else:
            tail = (completed.stderr or "").strip().splitlines()[-1:]
            report["failed"].append({"window": label, "codes": codes or ["exit_" + str(
                completed.returncode)], "detail": tail[0][:200] if tail else None})
            # A refusal that the next window would meet too stops the run; it resumes later.
            if set(codes) & {"gie_rate_limited", "gie_access_denied", "source_not_approved",
                             "gie_credential_missing", "certification_required"}:
                report["stopped"] = codes
        if not args.json:
            print(label, "ok" if label in str(report["done"][-1:]) else "failed", flush=True)
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if not report["failed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
