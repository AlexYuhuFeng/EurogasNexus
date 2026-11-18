"""Backfill ENTSOG physical flows at the landing points, a quarter per read, resumably.

The flows read compares pipeline landings with the last five complete gas years
(``application/fundamentals_flows.py``), so the landing registry's points
(``application/pipeline_supply.LANDING_POINTS``) need about six years of daily flows. This
driver gets them through the **existing** ingestion path: one call of
``scripts/ops/ingest_public_sources.py --source entsog`` per window, scoped to the landing
point-directions and a date range, so every rule of that path applies unchanged (the
administrator's approval, the certification gate, the operator's source switch, raw-page
archiving and the revision rules of ``docs/operations/DATA_REVISIONS.md``).

ENTSOG's terms and fair use (``docs/legal/DATA_SOURCE_TERMS.md``): the TP Terms of Use
(Rev. 3) Art. 5 permit storing and using the data with the source and download date cited;
the API manual (v2.1) asks that queries be filtered (dates, points, indicators) so they stay
within its 60-second timeout and share the platform fairly. Each call here is one quarter of
one indicator (physical flow) at the ten landing point-directions, at most 40 calls a run,
``--pace-seconds`` apart (default 3 s).

Resumable: a window whose (point, gas day) pairs the store already holds to 90 % is skipped.
``--refresh`` re-reads the last week (provider revisions; the scheduled ENTSOG run reads
seven days too). A refusal the next window would meet stops the run.

    python scripts/ops/backfill_entsog_landings.py --dry-run --json
    python scripts/ops/backfill_entsog_landings.py --years 5 --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST = ROOT / "scripts" / "ops" / "ingest_public_sources.py"
#: A quarter of a gas year per read (Oct-Dec, Jan-Mar, Apr-Jun, Jul-Sep).
QUARTER_MONTHS = ((10, 12), (1, 3), (4, 6), (7, 9))
HELD_SHARE = 0.9
REVISION_DAYS = 7
STOP_CODES = {"source_gate_blocked", "source_not_approved", "certification_required",
              "entsog_rate_limited", "source_disabled"}


@dataclass(frozen=True)
class Window:
    first: date
    last: date

    @property
    def days(self) -> int:
        return (self.last - self.first).days + 1


def point_directions() -> list[str]:
    """The landing registry's entry point-directions as ENTSOG spells them."""

    from eurogas_nexus.application.pipeline_supply import LANDING_POINTS

    return sorted({f"{p.operator}{p.point_id}entry".lower() for p in LANDING_POINTS})


def quarter_windows(years: int, today: date) -> list[Window]:
    """``years`` complete gas years and the current one, by quarter, ending yesterday."""

    current = today.year if today.month >= 10 else today.year - 1
    yesterday = today - timedelta(days=1)
    windows = []
    for gas_year in range(current - years, current + 1):
        for first_month, last_month in QUARTER_MONTHS:
            year = gas_year if first_month >= 10 else gas_year + 1
            first = date(year, first_month, 1)
            last_day = (date(year + (last_month == 12), last_month % 12 + 1, 1)
                        - timedelta(days=1))
            last = min(last_day, yesterday)
            if first <= last:
                windows.append(Window(first, last))
    return windows


def _gas_day(start: datetime) -> date:
    start = start.replace(tzinfo=UTC) if start.tzinfo is None else start.astimezone(UTC)
    return (start + timedelta(hours=7)).date()


def held_share(session, window: Window) -> float:
    """Share of the window's (landing point, gas day) pairs the store holds from ENTSOG."""

    from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
    from eurogas_nexus.db.models import FlowObservationRecord as Flow

    naive = session.get_bind().dialect.name == "sqlite"
    first = datetime.combine(window.first, datetime.min.time(), tzinfo=UTC) - timedelta(hours=8)
    last = datetime.combine(window.last, datetime.min.time(), tzinfo=UTC) + timedelta(hours=8)
    rows = (
        session.query(Flow.point_id, Flow.period_start_utc)
        .filter(Flow.source_system == "ENTSOG", Flow.direction.ilike("entry"))
        .filter(Flow.point_id.in_(sorted({p.point_id for p in LANDING_POINTS})))
        .filter(Flow.period_start_utc >= (first.replace(tzinfo=None) if naive else first))
        .filter(Flow.period_start_utc <= (last.replace(tzinfo=None) if naive else last))
        .all()
    )
    pairs = {(point, d) for point, start in rows
             if window.first <= (d := _gas_day(start)) <= window.last}
    expected = len({p.point_id for p in LANDING_POINTS}) * window.days
    return len(pairs) / expected if expected else 1.0


def newest_day(session) -> date | None:
    from sqlalchemy import func

    from eurogas_nexus.application.pipeline_supply import LANDING_POINTS
    from eurogas_nexus.db.models import FlowObservationRecord as Flow

    value = (
        session.query(func.max(Flow.period_start_utc))
        .filter(Flow.source_system == "ENTSOG")
        .filter(Flow.point_id.in_(sorted({p.point_id for p in LANDING_POINTS})))
        .scalar()
    )
    return _gas_day(value) if value is not None else None


def ingest_command(window: Window, directions: list[str]) -> list[str]:
    command = [
        sys.executable, str(INGEST), "--source", "entsog",
        "--entsog-from", window.first.isoformat(), "--entsog-to", window.last.isoformat(),
        "--limit", "5000", "--entsog-page-size", "1000", "--json",
    ]
    for direction in directions:
        command += ["--entsog-point-direction", direction]
    return command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--max-windows", type=int, default=40)
    parser.add_argument("--pace-seconds", type=float, default=3.0)
    parser.add_argument("--dry-run", action="store_true")
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
    directions = point_directions()
    with Session(get_engine(url)) as session:
        plan = [
            w for w in quarter_windows(args.years, today) if held_share(session, w) < HELD_SHARE
        ]
        newest = newest_day(session) if args.refresh else None
    if newest is not None:
        refresh = Window(newest - timedelta(days=REVISION_DAYS), today - timedelta(days=1))
        if refresh.first <= refresh.last and not any(
            w.first <= refresh.first and w.last >= refresh.last for w in plan
        ):
            plan.append(refresh)
    report: dict = {"ok": False, "planned": len(plan), "done": [], "failed": [],
                    "remaining": [], "stopped": None, "sources": {}}
    if args.dry_run:
        report["ok"] = True
        report["remaining"] = [f"{w.first}..{w.last}" for w in plan]
        print(json.dumps(report, indent=2) if args.json else f"{len(plan)} windows to read")
        return 0
    for position, window in enumerate(plan):
        label = f"{window.first}..{window.last}"
        if position >= args.max_windows or report["stopped"]:
            report["remaining"].append(label)
            continue
        if position:
            time.sleep(max(0.0, args.pace_seconds))
        completed = subprocess.run(  # noqa: S603 - our own script, fixed arguments
            ingest_command(window, directions), capture_output=True, text=True, cwd=ROOT,
            check=False,
        )
        try:
            outcome = json.loads(completed.stdout or "{}")
        except ValueError:
            outcome = {"failures": [{"code": "unreadable_report"}]}
        codes = sorted({str(f.get("code")) for f in outcome.get("failures") or []})
        for name, detail in (outcome.get("sources") or {}).items():
            if isinstance(detail, dict) and "records" in detail:
                report["sources"][f"{name} {label}"] = detail
        if completed.returncode == 0 and not codes:
            report["done"].append(label)
        else:
            tail = (completed.stderr or "").strip().splitlines()[-1:]
            report["failed"].append({"window": label, "codes": codes or [
                f"exit_{completed.returncode}"], "detail": tail[0][:200] if tail else None})
            if set(codes) & STOP_CODES:
                report["stopped"] = codes
        if not args.json:
            print(label, "ok" if label in report["done"] else "failed", flush=True)
    report["ok"] = not report["failed"] and not report["stopped"]
    if report["ok"] and not report["sources"]:
        report["sources"]["ENTSOG landings up to date"] = {"records": 0}
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
