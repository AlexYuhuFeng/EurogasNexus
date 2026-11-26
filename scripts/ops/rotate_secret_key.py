"""Re-encrypt every stored secret under the current deployment key (security review M9).

Rotation of ``EUROGAS_NEXUS_SECRET_KEY``:

1. Generate a new key; set it as ``EUROGAS_NEXUS_SECRET_KEY`` and put the old one in
   ``EUROGAS_NEXUS_SECRET_KEY_PREVIOUS``; restart. Everything still decrypts.
2. Run this command: provider credentials and second-factor secrets are re-encrypted under the
   new key (dry run by default; ``--commit`` writes).
3. Personal and service API keys hashed with the old key keep working while it is listed as
   previous; reissue them, then clear ``EUROGAS_NEXUS_SECRET_KEY_PREVIOUS`` and restart.

Prints counts only, never a secret.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def main(argv: list[str] | None = None) -> int:
    """Re-encrypt stored secrets; returns a process exit code."""

    from eurogas_nexus.db.models import IdentityMfaRecord, ProviderCredentialRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url
    from eurogas_nexus.security.credentials import reencrypt

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args(argv)
    if not resolve_database_url():
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    counts = {"provider_credentials": 0, "identity_mfa": 0, "failed": 0}
    with get_session_factory()() as session:
        for row in session.query(ProviderCredentialRecord).all():
            try:
                row.encrypted_payload = reencrypt(row.encrypted_payload)
                counts["provider_credentials"] += 1
            except Exception:  # noqa: BLE001 - counted, never printed
                counts["failed"] += 1
        for row in session.query(IdentityMfaRecord).all():
            try:
                row.secret_encrypted = reencrypt(row.secret_encrypted)
                counts["identity_mfa"] += 1
            except Exception:  # noqa: BLE001
                counts["failed"] += 1
        if args.commit and not counts["failed"]:
            session.commit()
        else:
            session.rollback()
    mode = "committed" if args.commit and not counts["failed"] else "dry-run"
    print(f"Re-encryption {mode}: {counts}")
    return 1 if counts["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
