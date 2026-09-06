"""Release compatibility evidence helper.

Prints the current application/schema/engine release manifest and checks that
the running (or imported) API resolves every declared permission. This is the
compatibility evidence required by the rollback runbook; actual previous-binary
rollback validation must be run against the deployment artifact and recorded
in docs/operations/RELEASE_ROLLBACK.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def current_git_sha() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def main() -> int:
    from apps.api.main import app
    from eurogas_nexus.release.constants import (
        API_CONTRACT_VERSION,
        BACKTEST_ENGINE_VERSION,
        DB_SCHEMA_REVISION,
        MINIMUM_SUPPORTED_CLIENT_VERSION,
        MINIMUM_SUPPORTED_SERVER_VERSION,
        STRATEGY_SCHEMA_VERSION,
    )
    from eurogas_nexus.security.permissions import permission_for_path

    paths = set(app.openapi()["paths"])
    for path in sorted(paths):
        permission_for_path(path)
    manifest = {
        "application_version": app.version,
        "git_sha": current_git_sha(),
        "public_paths": len(paths),
        "permission_registry": "complete",
        "api_contract_version": API_CONTRACT_VERSION,
        "database_schema_revision": DB_SCHEMA_REVISION,
        "minimum_supported_client": MINIMUM_SUPPORTED_CLIENT_VERSION,
        "minimum_supported_server": MINIMUM_SUPPORTED_SERVER_VERSION,
        "backtest_engine_version": BACKTEST_ENGINE_VERSION,
        "strategy_schema_version": STRATEGY_SCHEMA_VERSION,
    }
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
