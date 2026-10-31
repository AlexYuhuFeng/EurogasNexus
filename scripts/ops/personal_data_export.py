"""Export every stored record about one person (data-subject access request).

    python scripts/ops/personal_data_export.py --principal-id <id> --out dsar.json

Searches every table for columns that name a principal (principal_id, principal, actor,
created_by, updated_by, owner_principal_id, issued_by) or hold the person's e-mail, and
writes the matching rows as JSON. Secrets are never exported: columns whose names contain
hash, secret, token or password are replaced with "[withheld]". The export itself is
audited. Erasure is a separate, legal decision: records the firm must keep (audit trail,
decision records) are retained; identity data can then be disabled and minimised by an
administrator. See docs/compliance/COMPLIANCE_AUDIT.md.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, resolve_database_url

PERSON_COLUMNS = {
    "principal_id",
    "principal",
    "actor",
    "created_by",
    "updated_by",
    "owner_principal_id",
    "issued_by",
}
WITHHELD = ("hash", "secret", "token", "password")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--email", default=None)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    if not resolve_database_url():
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    from sqlalchemy import or_, select

    import eurogas_nexus.db.models  # noqa: F401  (register every table)
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.repositories.audit import record_audit_event

    found: dict[str, list[dict]] = {}
    with get_session_factory()() as session:
        for table in Base.metadata.sorted_tables:
            conditions = [
                column == args.principal_id
                for column in table.columns
                if column.name in PERSON_COLUMNS
            ]
            if args.email:
                conditions += [
                    column == args.email for column in table.columns if column.name == "email"
                ]
            if not conditions:
                continue
            rows = session.execute(select(table).where(or_(*conditions))).mappings().all()
            if rows:
                found[table.name] = [
                    {
                        key: "[withheld]"
                        if any(word in key.lower() for word in WITHHELD)
                        else value
                        for key, value in row.items()
                    }
                    for row in rows
                ]
        record_audit_event(
            session,
            event_type="privacy.access_request",
            principal="operator",
            action="personal_data.export",
            resource=f"identity_principal:{args.principal_id}",
            outcome="exported",
            severity="info",
            detail=f"tables={sorted(found)}",
            source_system="privacy-script",
            now_utc=datetime.now(UTC),
        )
        session.commit()
    report = {
        "principal_id": args.principal_id,
        "exported_at_utc": datetime.now(UTC).isoformat(),
        "tables": found,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"{sum(len(v) for v in found.values())} records from {len(found)} tables -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
