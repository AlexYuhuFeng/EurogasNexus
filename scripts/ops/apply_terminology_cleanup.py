#!/usr/bin/env python3
"""Verify the terminology cleanup and temporary API compatibility boundary."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE_COST = ROOT / "src/eurogas_nexus/api/routes/public/route_cost.py"
APP_TSX = ROOT / "clients/web/src/App.tsx"
LEGACY_FIELD = "research" + "_only"
COMPATIBILITY_LINE = f'            "{LEGACY_FIELD}": True,'


def main() -> int:
    route_text = ROUTE_COST.read_text(encoding="utf-8-sig")
    app_text = APP_TSX.read_text(encoding="utf-8-sig")

    compatibility_count = route_text.count(COMPATIBILITY_LINE)
    if compatibility_count != 1:
        raise RuntimeError(
            "Expected exactly one API-envelope compatibility field in "
            f"{ROUTE_COST.relative_to(ROOT)}; found {compatibility_count}"
        )
    if f'                "{LEGACY_FIELD}": True,' in route_text:
        raise RuntimeError("Legacy field remains in an endpoint business-data payload")
    if LEGACY_FIELD in app_text:
        raise RuntimeError(f"Legacy payload field remains in {APP_TSX.relative_to(ROOT)}")

    print("Terminology compatibility boundary verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
