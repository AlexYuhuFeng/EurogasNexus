#!/usr/bin/env python3
"""Remove the remaining legacy research-only payload field.

The script is deliberately conservative. It only applies the exact known backend
replacement and fails if that block has changed shape. Existing compatibility
routes and legitimate market-research capabilities are outside this cleanup.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTE_COST = ROOT / "src/eurogas_nexus/api/routes/public/route_cost.py"

LEGACY_BLOCK = (
    '            data = {\n'
    '                **contract,\n'
    '                "research_only": True,\n'
    '                "human_review_required": True,\n'
    '            }'
)
REPLACEMENT_BLOCK = (
    '            data = {\n'
    '                **contract,\n'
    '                "human_review_required": True,\n'
    '            }'
)


def main() -> int:
    text = ROUTE_COST.read_text(encoding="utf-8-sig")
    count = text.count(LEGACY_BLOCK)
    if count != 1:
        raise RuntimeError(
            f"Expected exactly one legacy block in {ROUTE_COST.relative_to(ROOT)}; found {count}"
        )

    updated = text.replace(LEGACY_BLOCK, REPLACEMENT_BLOCK, 1)
    if '"research_only": True' in updated:
        raise RuntimeError("Legacy route-cost response field remains after cleanup")

    ROUTE_COST.write_text(updated, encoding="utf-8")
    print(f"Updated: {ROUTE_COST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
