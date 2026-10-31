"""Load infrastructure locations from an openly licensed GeoJSON file (idempotent).

    python scripts/ops/import_infrastructure_geojson.py --file sodir_facilities.geojson \
        --dataset SODIR-FACILITIES --licence NLOD-2.0 \
        --attribution "Norwegian Offshore Directorate" --type production_platform --country NO

See ``eurogas_nexus.ingestion.infrastructure_geojson`` for accepted licences and sources.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.infrastructure_geojson import (
    InfrastructureImportError,
    parse_infrastructure,
)

MAX_BYTES = 256 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--file", required=True)
    parser.add_argument(
        "--dataset", required=True, help="Short dataset name, e.g. SODIR-FACILITIES"
    )
    parser.add_argument("--licence", required=True, help="CC-BY-4.0, ODbL-1.0, NLOD-2.0, ...")
    parser.add_argument("--attribution", required=True)
    parser.add_argument("--type", dest="facility_type", default=None)
    parser.add_argument("--country", default=None, help="ISO 3166 alpha-2 when not in the file")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        print(f"File missing or larger than {MAX_BYTES} bytes: {path}")
        return 2
    try:
        rows = parse_infrastructure(
            path.read_text(encoding="utf-8"),
            dataset=args.dataset,
            licence=args.licence,
            attribution=args.attribution,
            facility_type=args.facility_type,
            default_country=args.country,
        )
    except InfrastructureImportError as exc:
        print(f"Refused: {exc}")
        return 2
    print(f"{len(rows)} located facilities")
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import ReferenceFacility

    with get_session_factory(database_url=database_url)() as session:
        for row in rows:
            session.merge(ReferenceFacility(**row))
        session.commit()
    print(f"Loaded {len(rows)} facilities.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
