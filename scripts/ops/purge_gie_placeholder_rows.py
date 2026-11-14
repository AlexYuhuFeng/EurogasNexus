"""Remove stored GIE rows that carry no value (the provider's "no data" placeholders).

GIE answers a country/day it has no data for with a row whose every field is "-" (status
N): GB since Brexit, LNG for DK and LU. Before 2026-11-13 the ingestor stored them, so the
data-quality report counted them as blank days (7 % of AGSI rows, 20 % of ALSI rows). The
ingestor no longer stores them and no longer requests series GIE does not publish; this
removes the rows already stored.

Only ``source_system = 'GIE'`` rows with every value column empty are touched, and a row
with revision history in ``observation_revisions`` is kept (it once had a value). The raw
pages stay in the archive. Dry run by default; ``--commit`` deletes.

    python scripts/ops/purge_gie_placeholder_rows.py            # count only
    python scripts/ops/purge_gie_placeholder_rows.py --commit   # delete
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from sqlalchemy import and_, delete, exists, func, select

from eurogas_nexus.db.models import (
    LngObservationRecord,
    ObservationRevisionRecord,
    StorageObservationRecord,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url

_VALUE_COLUMNS = {
    StorageObservationRecord: (
        "inventory_twh",
        "working_capacity_twh",
        "fill_pct",
        "injection_twh_d",
        "withdrawal_twh_d",
    ),
    LngObservationRecord: ("inventory_twh", "send_out_twh_d", "dtmi_twh"),
}


def _placeholder_clause(model):
    columns = [getattr(model, name).is_(None) for name in _VALUE_COLUMNS[model]]
    revised = exists().where(
        ObservationRevisionRecord.observation_table == model.__tablename__,
        ObservationRevisionRecord.observation_id == model.observation_id,
    )
    return and_(model.source_system == "GIE", *columns, ~revised)


def purge(session, *, commit: bool) -> dict[str, dict[str, int]]:
    """Count (and with ``commit`` delete) valueless GIE rows, per table and country."""

    report: dict[str, dict[str, int]] = {}
    for model in _VALUE_COLUMNS:
        clause = _placeholder_clause(model)
        counts = session.execute(
            select(model.country, func.count()).where(clause).group_by(model.country)
        ).all()
        report[model.__tablename__] = {str(country): int(n) for country, n in counts}
        if commit and counts:
            session.execute(
                delete(model).where(clause), execution_options={"synchronize_session": False}
            )
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--commit", action="store_true", help="Delete (default: count only).")
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        print(json.dumps({"ok": False, "error": "database_url_missing"}))
        return 2
    with get_session_factory()() as session:
        report = purge(session, commit=args.commit)
        if args.commit:
            session.commit()
    print(json.dumps({"ok": True, "committed": args.commit, "valueless_rows": report}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
