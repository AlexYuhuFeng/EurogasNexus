"""Load GIE's AGSI+/ALSI facility listing as facility identity (EIC, name, country, operator).

Reads both listings with the registered GIE key (``GIE_API_KEY``, sent only in ``x-key``),
keeps one facility per EIC and upserts it into the identity tables
(``db/repositories/gie_facilities.py``): a canonical entity ``ent:gas_facility:<EIC>`` and a
``src-gie``/``gie_facility`` mapping. A facility no longer listed is retired, never deleted.
GIE publishes no coordinates: this gives the map a facility's identity, not a position
(``application/map_situation.py``, ``KNOWN_FACILITY_RULE``).

    python scripts/ops/ingest_gie_facilities.py                 # dry run: counts only
    python scripts/ops/ingest_gie_facilities.py --commit --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None, *, get_listing=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    parser.add_argument("--json", action="store_true", help="print a JSON report")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print

    from eurogas_nexus.ingestion.gie_facilities import (
        GieListingError,
        http_listing_getter,
        one_per_eic,
        parse_listing,
    )

    def fail(code: str) -> int:
        say(f"refused: {code}")
        if args.json:
            print(json.dumps({"ok": False, "failures": [{"code": code}], "sources": {}}))
        return 1

    owned = get_listing is None
    if owned:
        from eurogas_nexus.ingestion.gie_transport import resolve_gie_api_key

        key = resolve_gie_api_key()
        if key is None:
            say("GIE_API_KEY is not set; the facility listing needs the registered key.")
            return fail("gie_key_missing")
        get_listing = http_listing_getter(key.value)
    try:
        rows = [
            facility
            for kind in ("storage", "lng")
            for facility in parse_listing(get_listing(kind), kind)
        ]
    except GieListingError as exc:
        return fail(exc.code)
    finally:
        if owned:
            get_listing.close()
    if not rows:
        return fail("gie_listing_empty")
    facilities, repeated = one_per_eic(rows)
    now = datetime.now(UTC)
    by_kind = Counter(facility.kind for facility in facilities)
    say(
        f"{len(rows)} listed rows, {len(facilities)} facilities by EIC "
        f"(storage {by_kind['storage']}, LNG {by_kind['lng']}); listed twice: "
        f"{', '.join(repeated) or 'none'}"
    )
    counts = {"inserted": 0, "updated": 0, "unchanged": 0, "retired": 0, "restored": 0}
    if args.commit:
        from eurogas_nexus.db.repositories.gie_facilities import upsert_gie_facilities
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            counts = upsert_gie_facilities(session, facilities, now=now)
            session.commit()
        say(f"stored: {counts}")
    else:
        say("dry run (add --commit to store)")
    if args.json:
        print(json.dumps({
            "ok": True,
            "failures": [],
            "sources": {"gie_facilities": {
                "records": len(facilities), **counts, "listed_rows": len(rows),
                "listed_twice": repeated,
            }},
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
