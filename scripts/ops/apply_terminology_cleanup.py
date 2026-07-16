#!/usr/bin/env python3
"""Verify that legacy research-only payload fields are absent.

The source changes are already committed. This command is intentionally
idempotent so it can be used in local validation and CI without modifying files.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE_COST = ROOT / "src/eurogas_nexus/api/routes/public/route_cost.py"
APP_TSX = ROOT / "clients/web/src/App.tsx"
LEGACY_FIELD = "research" + "_only"


def main() -> int:
    offenders: list[str] = []
    for path in (ROUTE_COST, APP_TSX):
        if LEGACY_FIELD in path.read_text(encoding="utf-8-sig"):
            offenders.append(str(path.relative_to(ROOT)))

    if offenders:
        raise RuntimeError(f"Legacy payload field remains in: {', '.join(offenders)}")

    print("Terminology cleanup verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
