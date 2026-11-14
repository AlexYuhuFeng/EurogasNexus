"""Collect gas UMMs (storage and LNG unavailability) from GIE's Inside Information Platform.

Reads the IIP API newest-first until the window is covered, keeps unavailability reports
(every version, including the earlier versions IIP returns with each message), reads them
with the REMIT importer's normaliser and stores each version once. The key is GIE's
(``GIE_API_KEY``, or ``GIE_API_KEY_FILE``) and is sent only in the ``x-key`` header to
iip.gie.eu; it is never printed. GIE permits reuse with GIE named as the source.

    python scripts/ops/ingest_remit_iip.py --days 7              # dry run: counts only
    python scripts/ops/ingest_remit_iip.py --days 7 --commit --json
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


def main(argv: list[str] | None = None, *, get_page=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=2, help="submissions in the last N days")
    parser.add_argument("--max-pages", type=int, default=40, help="read bound (50 per page)")
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print
    if args.days < 1 or args.max_pages < 1:
        parser.error("--days and --max-pages must be at least 1")

    from eurogas_nexus.domain.observations.remit_platforms import source_reference_for
    from eurogas_nexus.domain.observations.remit_umm import (
        UmmParseError,
        current_messages,
        parse_umm_export,
    )
    from eurogas_nexus.ingestion.gie_iip import (
        IipError,
        acer_messages,
        fetch_iip_messages,
        http_page_getter,
    )

    def fail(code: str) -> int:
        say(f"refused: {code}")
        if args.json:
            print(json.dumps({"ok": False, "failures": [{"code": code}], "sources": {}}))
        return 1

    now = datetime.now(UTC)
    owned_getter = get_page is None
    if owned_getter:
        from eurogas_nexus.ingestion.gie_transport import resolve_gie_api_key

        key = resolve_gie_api_key()
        if key is None:
            say("GIE_API_KEY is not set; IIP requires the registered key (x-key).")
            return fail("iip_key_missing")
        get_page = http_page_getter(key.value)
    try:
        read = fetch_iip_messages(get_page, since=now - timedelta(days=args.days),
                                  max_pages=args.max_pages)
    except IipError as exc:
        return fail(exc.code)
    finally:
        if owned_getter:
            get_page.close()

    fields = acer_messages(read.records)
    reference = source_reference_for("GIE_IIP", f"api:{now:%Y%m%dT%H%MZ}", terms_confirmed=False)
    try:
        messages = (
            parse_umm_export(json.dumps(fields), source_reference=reference) if fields else []
        )
    except UmmParseError as exc:
        say(f"refused: {exc}")
        return fail("iip_umm_unreadable")
    live = current_messages(messages)
    say(
        f"{read.pages} pages ({read.stop}), {len(read.records)} messages, "
        f"{len(messages)} unavailability versions, {len(live)} current events"
    )
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    if args.commit and messages:
        from eurogas_nexus.db.repositories.remit import store_umm_messages
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            counts = store_umm_messages(session, messages, now=now)
            session.commit()
        say(f"stored: {counts}")
    elif not args.commit:
        say("dry run (add --commit to store)")
    if args.json:
        print(json.dumps({
            "ok": bool(read.records),
            "failures": [] if read.records else [{"code": "iip_no_messages"}],
            "sources": {"gie_iip": {"records": len(messages), **counts, "revised": 0}},
        }, sort_keys=True))
    return 0 if read.records else 1


if __name__ == "__main__":
    raise SystemExit(main())
