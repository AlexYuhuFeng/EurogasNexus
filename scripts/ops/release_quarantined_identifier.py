"""Release a quarantined provider identifier by recording its mapping (ONT-02).

A stored row whose provider identifier does not resolve is withheld from every reader
(``application/identity_resolution.WITHHOLDING_RULE``) and listed on the Sources page under
``unresolved_identifiers``. When an operator has established what the identifier names (for
example an ENTSOG point key the reference no longer lists, checked against the operator's
own publication), this records an ``ACTIVE`` row in ``source_entity_mappings`` for it, and
its rows are served from the next read. Nothing in the stored observations changes.

Dry run by default: prints the identifier's current resolution and the rows withheld per
table before and after, then rolls back. ``--commit`` keeps the mapping. ``--evidence``
is required and is stored on the mapping (who checked what).

    python scripts/ops/release_quarantined_identifier.py --source-id src-entsog \
        --entity-type entsog_point --identifier ITP-00044 \
        --evidence "Dragor: ENTSOG 2019 reference, checked by <name>"
    ... --commit

To withdraw a release, set the mapping's ``mapping_status`` to ``RETIRED`` (or its
``valid_to_utc``); the rows are withheld again on the next read.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from eurogas_nexus.application.identity_resolution import (
    identity_report,
    load_resolver,
    record_identities,
    withheld_counts,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.domain.ontology.source_identity import (
    ENTITY_PREFIX,
    SourceIdentity,
    canonical_id,
)


def release(
    session,
    *,
    source_id: str,
    entity_type: str,
    identifiers: Sequence[str],
    evidence: str,
    canonical: str | None = None,
    commit: bool = False,
) -> dict:
    """Map each identifier (dry run unless ``commit``) and report withheld rows around it."""

    resolver = load_resolver(session)
    before = withheld_counts(session)
    current = {
        identifier: resolver.resolve(source_id, entity_type, identifier).__dict__
        for identifier in identifiers
    }
    items = [
        SourceIdentity(
            source_id,
            entity_type,
            identifier,
            canonical or canonical_id(entity_type, identifier),
            f"Operator release: {evidence}"[:512],
        )
        for identifier in identifiers
    ]
    written = record_identities(session, items)
    after = withheld_counts(session)
    unresolved = identity_report(session).get(source_id, {}).get("unresolved", [])
    if commit:
        session.commit()
    else:
        session.rollback()
    return {
        "ok": True,
        "committed": commit,
        "resolution_before": current,
        "mappings": written,
        "withheld_rows_before": before,
        "withheld_rows_after": after,
        "still_unresolved": len(unresolved),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--source-id", required=True, help="e.g. src-entsog")
    parser.add_argument(
        "--entity-type", required=True, choices=sorted(ENTITY_PREFIX), help="e.g. entsog_point"
    )
    parser.add_argument("--identifier", action="append", required=True,
                        help="Provider identifier; repeat for several.")
    parser.add_argument("--canonical", default=None,
                        help="Canonical entity id (default: the type's id for the identifier).")
    parser.add_argument("--evidence", required=True, help="Who established what, and how.")
    parser.add_argument("--commit", action="store_true", help="Keep the mapping.")
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        print(json.dumps({"ok": False, "error": "database_url_missing"}))
        return 2
    if args.canonical and len(args.identifier) > 1:
        print(json.dumps({"ok": False, "error": "one_canonical_for_several_identifiers"}))
        return 2
    with get_session_factory()() as session:
        report = release(
            session,
            source_id=args.source_id,
            entity_type=args.entity_type,
            identifiers=args.identifier,
            evidence=args.evidence,
            canonical=args.canonical,
            commit=args.commit,
        )
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
