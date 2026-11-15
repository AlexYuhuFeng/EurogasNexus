"""Audit stored rows that name a Danish hub (ETF, GTF, Gaspoint Nordic): before and after.

Until 2026-11-15 the market registry listed ``ETF`` as an alias of TTF, so a contract,
screen trade or quote written "ETF" was resolved to the Dutch hub and valued at TTF. ETF is
the Danish Exchange Transfer Facility and GTF the Danish bilateral Gas Transfer Facility;
neither is TTF and they are not each other. This lists every stored row whose text names
ETF, GTF, Gaspoint Nordic or the facilities' full names, with:

- ``before``: the hub the old rule resolved it to (ETF -> TTF; GTF and Gaspoint unresolved);
- ``after``: the hub the ontology resolves it to now (with the deployment's mappings);
- ``stored_hub``: the row's own hub column, where the table has one.

Read-only by default. A stored hub column is corrected only where it holds TTF while the
row's own text resolves to a Danish hub, and only with ``--commit``; contracts store a
delivery-point name, not a hub, and are resolved at read time, so they need no write.

    python scripts/ops/audit_danish_hub_references.py            # JSON report, no write
    python scripts/ops/audit_danish_hub_references.py --commit   # also correct hub columns
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Sequence

from sqlalchemy import inspect

from eurogas_nexus.db.session import get_session_factory, resolve_database_url

DANISH = re.compile(
    r"(?<![A-Za-z0-9])(ETF|GTF|GASPOINT)(?![A-Za-z0-9])"
    r"|exchange transfer facility|gas transfer facility|gaspoint nordic",
    re.IGNORECASE,
)
DANISH_HUBS = frozenset({"ETF", "GTF"})


def legacy_hub(text: str | None, after: str | None) -> str | None:
    """The hub the pre-2026-11-15 registry gave this text: ETF was an alias of TTF.

    GTF and Gaspoint were not registered, so they did not resolve; any other hub is as now.
    """

    if after == "ETF":
        named_etf = re.search(r"(?<![A-Za-z0-9])ETF(?![A-Za-z0-9])", str(text or ""), re.I)
        return "TTF" if named_etf else None
    if after == "GTF":
        return None
    return after


def _tables(session):
    from eurogas_nexus.db.models import (
        MarketObservationRecord,
        MarketQuoteRecord,
        ScreenOrderObservationRecord,
        TraderMandateRecord,
        UpstreamResourceContractRecord,
    )

    return (
        # (label, model, id column, text columns, stored hub column or None)
        ("contracts", UpstreamResourceContractRecord, "contract_id",
         ("delivery_point_name", "contract_name"), None),
        ("screen_trades", ScreenOrderObservationRecord, "order_observation_id",
         ("product", "contract_code", "hub"), "hub"),
        ("quotes", MarketQuoteRecord, "quote_id", ("product", "instrument_id", "hub"), "hub"),
        ("observations", MarketObservationRecord, "observation_id", ("product",), None),
        ("mandates", TraderMandateRecord, "mandate_id", ("display_name",), None),
    )


def audit(session, *, commit: bool = False) -> dict:
    from eurogas_nexus.application.identity_resolution import load_resolver

    resolver = load_resolver(session)
    inspector = inspect(session.connection())
    report: dict = {"tables": {}, "corrections": [], "committed": commit}
    for label, model, id_column, text_columns, hub_column in _tables(session):
        if not inspector.has_table(model.__tablename__):
            continue
        columns = [c for c in text_columns if hasattr(model, c)]
        rows = []
        for record in session.query(model).all():
            texts = [str(getattr(record, c) or "") for c in columns]
            metadata = getattr(record, "metadata_json", None) or {}
            if isinstance(metadata, dict) and metadata.get("hub"):
                texts.append(str(metadata["hub"]))
            hubs_list = getattr(record, "hubs", None) if label == "mandates" else None
            if hubs_list:
                texts.append(" ".join(map(str, hubs_list)))
            text = " | ".join(t for t in texts if t)
            if not DANISH.search(text):
                continue
            # The text a reader resolves: the delivery point, the product or the hub field.
            subject = texts[0] if label != "mandates" else text
            after = resolver.hub(subject).hub
            entry = {
                "id": getattr(record, id_column),
                "text": text[:200],
                "before": legacy_hub(subject, after),
                "after": after,
            }
            if hub_column:
                stored = str(getattr(record, hub_column) or "").upper()
                entry["stored_hub"] = stored
                product_hub = resolver.hub(" ".join(texts[:2])).hub
                if stored == "TTF" and product_hub in DANISH_HUBS:
                    report["corrections"].append(
                        {"table": model.__tablename__, "id": entry["id"],
                         "column": hub_column, "from": stored, "to": product_hub}
                    )
                    if commit:
                        setattr(record, hub_column, product_hub)
            rows.append(entry)
        report["tables"][label] = {
            "rows": len(rows),
            "changed_resolution": sum(1 for r in rows if r["before"] != r["after"]),
            "items": rows,
        }
    if commit:
        session.commit()
    else:
        session.rollback()
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--commit", action="store_true",
                        help="Correct stored hub columns that hold TTF for a Danish product.")
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        print(json.dumps({"ok": False, "error": "database_url_missing"}))
        return 2
    with get_session_factory()() as session:
        report = audit(session, commit=args.commit)
    print(json.dumps({"ok": True, **report}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
