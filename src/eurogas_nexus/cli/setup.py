"""First-run setup from the server's shell (headless installs).

Keys are set in the environment or key files (``EUROGAS_NEXUS_*``/provider variables, see
``deploy/runtime/env.server.example``) or with the Credentials API; approvals with
``scripts/ops/approve_public_source.py``. This records the flow itself, so administrators of
a headless install are not shown the welcome flow at sign-in::

    python -m eurogas_nexus.cli.setup status
    python -m eurogas_nexus.cli.setup complete     # configured from the environment
    python -m eurogas_nexus.cli.setup reopen       # show it again at the next admin sign-in
"""

from __future__ import annotations

import argparse
import getpass
import json


def main(argv: list[str] | None = None) -> int:
    from eurogas_nexus.application import first_run_setup
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    parser = argparse.ArgumentParser(prog="python -m eurogas_nexus.cli.setup")
    parser.add_argument("command", choices=("status", "complete", "reopen"))
    args = parser.parse_args(argv)
    if resolve_database_url() is None:
        raise SystemExit("RUNTIME_STORE_DATABASE_URL is not set: point it at the runtime database")
    try:
        actor = f"cli:{getpass.getuser()}"[:80]
    except Exception:  # noqa: BLE001
        actor = "cli:operator"
    with get_session_factory()() as session:
        if args.command == "complete":
            first_run_setup.update_setup_state(
                session, status="completed", step=None, actor=actor, configured_by="environment"
            )
        elif args.command == "reopen":
            first_run_setup.update_setup_state(
                session, status="in_progress", step="welcome", actor=actor
            )
        session.commit()
        print(json.dumps(first_run_setup.setup_state(session), indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
