"""Collect transmission UMMs (urgent market messages) from the ENTSOG Transparency Platform.

Reads ENTSOG's ``urgentmarketmessages`` dataset in full through the ENTSOG transport (the
dataset is small: 93 versions on 2026-11-16), keeps the unavailability messages published in
the window or still running after its start, reads them with the REMIT importer's normaliser
and stores each version once (``db/repositories/remit.py``, system ``ENTSOG_UMM``). No key.
Terms: ENTSOG TP Art. 5, cite "ENTSOG TP [DD-MM-YYYY] https://transparency.entsog.eu/"; the
download date is in every stored message's source reference.

The publisher's ENTSOG operator key is checked against the identities the ENTSOG reference
read wrote (``source_entity_mappings``); a message whose operator does not resolve is left
out and listed under ``quarantined``. Before the store holds any ENTSOG operator mapping,
nothing can be judged and nothing is left out (as for ENTSOG flows). A message whose newest
version in the feed ENTSOG flags as not the latest is also left out
(``latest_version_not_published``): its current state is not published.

    python scripts/ops/ingest_remit_entsog.py --days 90               # dry run: counts only
    python scripts/ops/ingest_remit_entsog.py --days 7 --commit --json
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

SYSTEM = "ENTSOG_UMM"


def _resolver(commit: bool):
    """The store's identity mappings, or an empty resolver when there is no store."""

    from eurogas_nexus.application.identity_resolution import IdentityResolver, load_resolver

    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return load_resolver(session)
    except Exception:  # noqa: BLE001 - a dry run without a configured store still reads
        if commit:
            raise
        return IdentityResolver()


def main(argv: list[str] | None = None, *, client=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=7,
                        help="versions published in, or events running after, the last N days")
    parser.add_argument("--max-pages", type=int, default=10, help="read bound (100 per page)")
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print
    if args.days < 1 or not 1 <= args.max_pages <= 50:
        parser.error("--days must be at least 1 and --max-pages between 1 and 50")

    from eurogas_nexus.application.identity_resolution import check_identifiers
    from eurogas_nexus.domain.observations.remit_platforms import source_reference_for
    from eurogas_nexus.domain.observations.remit_umm import (
        UmmParseError,
        current_messages,
        parse_umm_export,
    )
    from eurogas_nexus.ingestion.entsog_transport import (
        EntsogTransportError,
        fetch_entsog_dataset,
    )
    from eurogas_nexus.ingestion.entsog_umm import (
        DATASET,
        PAGE_SIZE,
        acer_messages,
        citation,
        records_of,
        threads_without_latest,
    )

    def fail(code: str) -> int:
        say(f"refused: {code}")
        if args.json:
            print(json.dumps({"ok": False, "failures": [{"code": code}], "sources": {}}))
        return 1

    now = datetime.now(UTC)
    owned = client is None
    if owned:
        import httpx

        from eurogas_nexus.core.outbound_http import client_options
        from eurogas_nexus.ingestion.entsog_transport import ENTSOG_BASE_URL

        client = httpx.Client(follow_redirects=False, trust_env=False,
                              **client_options(ENTSOG_BASE_URL))
    try:
        result = fetch_entsog_dataset(
            client, DATASET, page_size=PAGE_SIZE, max_records=PAGE_SIZE * args.max_pages,
            max_pages=args.max_pages, timeout_seconds=60.0,
        )
    except EntsogTransportError as exc:
        return fail(exc.code)
    finally:
        if owned:
            client.close()
    if not result.complete:
        return fail("entsog_umm_read_bound_reached")

    records = records_of(result)
    fields = acer_messages(records, since=now - timedelta(days=args.days))
    resolver = _resolver(args.commit)
    judged = any(
        source == "src-entsog" and kind == "entsog_operator"
        for source, kind, _identifier in resolver.mappings
    )
    operators = {
        str(record.get("marketParticipantKey") or ""): None for record in records
    }
    identity = check_identifiers("src-entsog", "entsog_operator", list(operators), resolver)
    unresolved = {item["identifier"] for item in identity["quarantined"]} if judged else set()
    key_by_message = {
        str(record.get("threadId") or ""): str(record.get("marketParticipantKey") or "")
        for record in records
    }
    quarantined: list[dict] = [
        {"message_id": item["messageId"], "reason": "unresolved_operator",
         "detail": key_by_message.get(item["messageId"], "")}
        for item in fields
        if key_by_message.get(item["messageId"], "") in unresolved
    ]
    # The provider flags no held version as the latest: the event's state is not published.
    orphaned = threads_without_latest(records)
    quarantined += [
        {"message_id": thread, "reason": "latest_version_not_published",
         "detail": f"newest held version {version} is flagged isLatestVersion=No"}
        for thread, version in sorted(orphaned.items())
        if any(item["messageId"] == thread for item in fields)
    ]
    held = {item["message_id"] for item in quarantined}
    fields = [item for item in fields if item["messageId"] not in held]

    reference = source_reference_for("ENTSOG_TP", f"api:{now:%Y%m%dT%H%MZ}",
                                     terms_confirmed=False)
    try:
        messages = (
            parse_umm_export(json.dumps(fields), source_reference=reference,
                             quarantine=quarantined)
            if fields
            else []
        )
    except UmmParseError as exc:
        say(f"refused: {exc}")
        return fail("entsog_umm_unreadable")
    live = current_messages(messages)
    for item in quarantined:
        say(f"quarantined {item['message_id']}: {item['reason']} ({item['detail']})")
    say(
        f"{len(result.pages)} pages ({result.stop_reason}), {len(records)} message versions, "
        f"{len(messages)} unavailability versions in the window, {len(live)} current events; "
        f"operators {identity['resolved']}/{identity['checked']} resolved"
        + ("" if judged else " (no ENTSOG reference mappings yet: not judged)")
    )
    counts = {"inserted": 0, "updated": 0, "unchanged": 0}
    if args.commit and messages:
        from eurogas_nexus.db.repositories.remit import store_umm_messages
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            counts = store_umm_messages(session, messages, now=now, source_system=SYSTEM)
            session.commit()
        say(f"stored: {counts}")
    elif not args.commit:
        say("dry run (add --commit to store)")
    say(f"cite as: {citation(now)}")
    if args.json:
        print(json.dumps({
            "ok": True,
            "failures": [],
            "sources": {"entsog_umm": {
                "records": len(messages), **counts, "revised": 0,
                "provider_versions": len(records), "identity": identity,
            }},
            "quarantined": quarantined,
            "citation": citation(now),
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
