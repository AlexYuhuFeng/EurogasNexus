"""Import REMIT gas UMMs (outages) exported from an inside-information platform.

Operators of gas production, storage, LNG and transmission facilities publish unavailability
as urgent market messages under REMIT. Export them from the platform your desk follows
(EEX Transparency, GIE IIP, Gassco UMM...) as JSON or CSV in ACER's fields and import them
here; each message version is stored once, and Market → Capacity & Events shows the latest
version of each live or upcoming event. The platform is recorded with every message;
platforms whose reuse terms are not published need ``--terms-confirmed`` (see
``eurogas_nexus.domain.observations.remit_platforms``).

    python scripts/ops/import_remit_umm.py --platform GIE_IIP --file iip_umm.json
    python scripts/ops/import_remit_umm.py --platform EEX_TP --terms-confirmed --file eex.csv
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.observations.remit_platforms import (
    REMIT_PLATFORMS,
    source_reference_for,
)
from eurogas_nexus.domain.observations.remit_umm import (
    UmmParseError,
    current_messages,
    parse_umm_export,
)

MAX_EXPORT_BYTES = 16 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    """Parse and store one export; returns a process exit code."""

    args = _parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        print(f"Export file missing or larger than {MAX_EXPORT_BYTES} bytes: {path}")
        return 2
    try:
        reference = source_reference_for(
            args.platform, path.name, terms_confirmed=args.terms_confirmed
        )
    except ValueError as exc:
        print(f"Refused: {exc}")
        return 2
    try:
        messages = parse_umm_export(
            path.read_text(encoding="utf-8"),
            source_reference=args.source_reference or reference,
        )
    except UmmParseError as exc:
        print(f"Refused: {exc}")
        return 2
    live = current_messages(messages)
    print(
        f"{len(messages)} message versions, {len(live)} current events, "
        f"assets={len({m.asset_name for m in live})}"
    )
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import RemitUmmRecord

    now = datetime.now(UTC)
    with get_session_factory(database_url=database_url)() as session:
        for message in messages:
            session.merge(
                RemitUmmRecord(**message.as_record(), source_system="REMIT", ingested_at_utc=now)
            )
        session.commit()
    print(f"Stored {len(messages)} REMIT message versions.")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True, help="JSON or CSV export of gas UMMs")
    parser.add_argument(
        "--platform", required=True, choices=sorted(REMIT_PLATFORMS), help="Where it came from"
    )
    parser.add_argument(
        "--terms-confirmed",
        action="store_true",
        help="The platform has confirmed commercial reuse in writing",
    )
    parser.add_argument("--source-reference", default=None, help="Provenance label to store")
    parser.add_argument("--dry-run", action="store_true", help="Parse and report only")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
