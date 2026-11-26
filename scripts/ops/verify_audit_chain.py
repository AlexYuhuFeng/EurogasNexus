"""Verify the audit trail's hash chain, optionally recording a signed checkpoint.

Security review H5. Exit code 0 when the chain verifies, 1 when it is broken, 2 when the
runtime database is not configured. Prints a JSON summary (no event content).

Usage:
    python scripts/ops/verify_audit_chain.py
    python scripts/ops/verify_audit_chain.py --checkpoint   # seal, verify, record the head
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def main(argv: list[str] | None = None) -> int:
    """Verify (and optionally checkpoint) the chain; returns a process exit code."""

    from eurogas_nexus.db import audit_chain
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--checkpoint", action="store_true")
    args = parser.parse_args(argv)
    if not resolve_database_url():
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    with get_session_factory()() as session:
        if args.checkpoint:
            result = audit_chain.checkpoint(session, by="verify-cli")
            session.commit()
        else:
            result = audit_chain.verify_chain(session)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
