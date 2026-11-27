"""The small-desk status facts as one JSON line, for ``nexus status`` (``deploy/small-desk``).

Run in the API container::

    python -m eurogas_nexus.cli.desk_status

The facts and their collection are ``application/desk_status.py``. Prints no setting, URL or
credential; exits 0 even when a part is unhealthy (judging is the caller's job), 2 when no
database is configured.
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str] | None = None) -> int:
    del argv
    from eurogas_nexus.application.desk_status import collect
    from eurogas_nexus.db.session import resolve_database_url

    if not resolve_database_url():
        print(json.dumps({"errors": ["database: not configured"]}))
        return 2
    from eurogas_nexus.security.portfolio_scope import system_scope

    # Operational metadata only (revision, heartbeat, source receipts, the backup marker);
    # read in the system scope like the gated upgrade, so book isolation never hides a row.
    with system_scope():
        print(json.dumps(collect(), sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
