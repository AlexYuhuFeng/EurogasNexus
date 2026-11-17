"""Approve a public source for your firm so live ingestion may read it (headless installs).

The same step as Admin -> Connectors -> "Approve this public source", for an installation
without a browser at hand. ENTSOG and GIE are read only after an administrator approved
them (the fail-closed ingestion gate); every other public source needs no approval.

    # what needs approval, its state and each provider's terms summary
    python scripts/ops/approve_public_source.py --list

    # approve one source (or --all-open for every source not approved yet)
    python scripts/ops/approve_public_source.py --source entsog --operator ops.name \\
        --reason "first run, ticket OPS-12" --accept-terms

``--accept-terms`` states that you read the terms summary printed by ``--list`` and accept
it for your firm; without it nothing is recorded. The approval records who, when, why and
which summary was shown, writes the audit event ``source.approval`` and runs the bounded
live validation (a small live sample and a normaliser dry run; nothing is stored). GIE
needs its key (``GIE_API_KEY``, ``GIE_API_KEY_FILE`` or the Credentials screen): approved
before the key exists it reads "approved, waiting for key" and is validated at the first
read after the key arrives. Repeating an approval that is in force changes nothing.
Exit 0 when every named source is approved (validated or waiting for its key), 1 when a
validation failed, 2 for a usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def _states(session) -> list[dict]:
    from eurogas_nexus.application.public_source_approval import resolve_provider_key
    from eurogas_nexus.db.repositories.certification import latest_certification
    from eurogas_nexus.domain.ingestion.certification import certification_gate
    from eurogas_nexus.domain.ingestion.source_approval import (
        APPROVAL_SOURCE_IDS,
        STATE_WORDS,
        approval_state,
    )

    rows = []
    for system, source_id in sorted(APPROVAL_SOURCE_IDS.items()):
        record = latest_certification(session, system)
        gate = certification_gate(
            system, stage=(record or {}).get("stage", ""), checks=(record or {}).get("checks")
        )
        key_state = (
            "not_required" if system != "GIE"
            else "configured" if resolve_provider_key(system) else "missing"
        )
        state = approval_state(
            system, certification=record, gate_allows_live=gate.allows_live,
            credential_state=key_state, connectivity_status="",
        )
        rows.append({"source_id": source_id, "source_system": system,
                     "state_words": STATE_WORDS[state["state"]], **state})
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--list", action="store_true", help="show state and terms; change nothing")
    target.add_argument("--source", action="append", help="entsog or gie (repeatable)")
    target.add_argument("--all-open", action="store_true",
                        help="every public source not approved yet")
    parser.add_argument("--operator", help="who approves (recorded and audited)")
    parser.add_argument("--reason", help="why (recorded and audited)")
    parser.add_argument("--accept-terms", action="store_true",
                        help="you read the terms summary (--list) and accept it for your firm")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    from eurogas_nexus.application.public_source_approval import (
        ApprovalError,
        approve_public_source,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        print("RUNTIME_STORE_DATABASE_URL is not set.", file=sys.stderr)
        return 2
    factory = get_session_factory()
    with factory() as session:
        states = _states(session)
    if args.list:
        if args.json:
            print(json.dumps(states, indent=2, ensure_ascii=False))
        else:
            for row in states:
                terms = row.get("terms") or {}
                print(f"{row['source_id']}: {row['state_words']}"
                      + (f" (by {row['approved_by']})" if row.get("approved_by") else ""))
                print(f"  terms ({terms.get('provider')}): {terms.get('summary')}")
                print(f"  attribution: {terms.get('attribution')}  [{terms.get('terms_url')}]")
        return 0
    if not (args.operator and args.reason):
        parser.error("--operator and --reason are required to approve")
    sources = args.source or [
        row["source_id"] for row in states if row["state"] == "not_approved"
    ]
    if not args.accept_terms:
        for row in states:
            if row["source_id"] in sources or row["source_system"].lower() in sources:
                terms = row.get("terms") or {}
                print(f"{row['source_id']} terms: {terms.get('summary')}", file=sys.stderr)
        print("Nothing recorded: add --accept-terms to accept these terms for your firm.",
              file=sys.stderr)
        return 2
    results, failed = [], False
    for source in sources:
        try:
            with factory() as session:
                result = approve_public_source(
                    session, source, actor=args.operator, reason=args.reason,
                    accept_terms=True,
                )
                session.commit()
        except ApprovalError as exc:
            print(f"{source}: {exc.code}: {exc}", file=sys.stderr)
            return 2
        failed = failed or result["state"] == "failing"
        results.append(result)
        if not args.json:
            note = "" if result["changed"] else " (already approved; nothing changed)"
            print(f"{result['source_id']}: {result['state']}{note}"
                  + (f" - {result['failure']}" if result.get("failure") else ""))
    if args.json:
        print(json.dumps({"ok": not failed, "results": results}, indent=2, ensure_ascii=False))
    elif not sources:
        print("Every public source is already approved.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
