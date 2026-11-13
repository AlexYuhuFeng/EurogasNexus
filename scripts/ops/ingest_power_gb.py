"""Ingest Great Britain power from Elexon: gas and wind generation, demand, market index.

    python scripts/ops/ingest_power_gb.py --days 7 --commit

No key is needed. ENTSO-E does not carry GB; this is the GB side of gas-for-power.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=2, help="settlement days ending today")
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print

    from eurogas_nexus.ingestion.elexon_insights import (
        PARSERS,
        ElexonParseError,
        fetch_json,
        request_urls,
    )

    today = datetime.now(UTC).date()
    first = today - timedelta(days=max(0, args.days - 1))
    observations, failures = [], []
    # One settlement day per request keeps each response small and a failure local.
    day = first
    while day <= today:
        for name, url in request_urls(day, day).items():
            try:
                observations += PARSERS[name](fetch_json(url), reference=f"elexon:{name}:{day}")
            except (OSError, ValueError, ElexonParseError) as exc:
                failures.append({"source": f"elexon:{name}:{day}", "code": type(exc).__name__})
                say(f"elexon:{name}:{day}: {type(exc).__name__}: {str(exc)[:160]}")
        day += timedelta(days=1)

    # The price read is inclusive at both ends, so midnight comes back with each day.
    observations = list({item.observation_id: item for item in observations}.values())
    counts: dict[str, int] = {}
    for item in observations:
        counts[item.metric] = counts.get(item.metric, 0) + 1
    for metric, count in sorted(counts.items()):
        say(f"GB     {metric:24} {count:6d}")
    stored = {"inserted": 0, "updated": 0, "unchanged": 0}
    if args.commit:
        from eurogas_nexus.db.repositories.power import upsert_power_observations
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            stored = upsert_power_observations(session, observations, source_system="ELEXON")
            session.commit()
        say(f"stored: {stored}")
    else:
        say(f"{len(observations)} observations parsed; dry run (add --commit to store)")
    ok = bool(observations) and not failures
    if args.json:
        print(json.dumps({"ok": ok, "failures": failures,
                          "sources": {"elexon": {"records": len(observations), **stored}}}))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
