#!/usr/bin/env python3
"""Wire extracted App builders into clients/web/src/App.tsx.

This script is intentionally conservative:
- it reads the local full App.tsx file instead of relying on partial GitHub snippets;
- every replacement must match exactly once;
- the script fails before writing if any expected block is missing;
- the resulting App.tsx must not contain the legacy research-only payload flag.
"""

from __future__ import annotations

import codecs
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP_TSX = ROOT / "clients" / "web" / "src" / "App.tsx"

APP_IMPORT = '''import {
  buildContractPayload,
  buildResourcePoolOptimizationRequest,
  buildRouteRecommendationRequest,
  buildStrategyScenario,
} from "@/app";
'''

IMPORT_ANCHOR = 'import { WorkspaceTopBar, type WorkspacePageId } from "@/components/WorkspaceTopBar";\n'

RESOURCE_POOL_PATTERN = re.compile(
    r'''  const resourcePoolOptimizationRequest = useMemo\(\(\) => \(\{\n'''
    r'''    portfolio_id: "web-resource-pool",\n'''
    r'''    resources: portfolioResources,\n'''
    r'''    sale_options: saleOptions,\n'''
    r'''    annual_financing_rate_pct: upstreamContracts\[0\]\?\.annual_financing_rate_pct \?\? contract\.annual_financing_rate_pct,\n'''
    r'''    objective: "MAX_DAILY_PNL",\n'''
    r'''    research_only: true,\n'''
    r'''  \}\), \[contract\.annual_financing_rate_pct, portfolioResources, saleOptions, upstreamContracts\]\);'''
)

RESOURCE_POOL_REPLACEMENT = '''  const resourcePoolOptimizationRequest = useMemo(
    () => buildResourcePoolOptimizationRequest(contract, portfolioResources, saleOptions, upstreamContracts),
    [contract, portfolioResources, saleOptions, upstreamContracts],
  );'''

CONTRACT_PAYLOAD_PATTERN = re.compile(
    r'''  const contractPayload = useMemo\(\(\) => \(\{\n[\s\S]*?\n  \}\), \[contract\]\);'''
)

CONTRACT_PAYLOAD_REPLACEMENT = '''  const contractPayload = useMemo(() => buildContractPayload(contract), [contract]);'''

STRATEGY_SCENARIO_PATTERN = re.compile(
    r'''  const strategyScenario = useMemo\(\(\) => \{\n[\s\S]*?\n  \}, \[contract, liveMark, markets, portfolioResources\]\);'''
)

STRATEGY_SCENARIO_REPLACEMENT = '''  const strategyScenario = useMemo(
    () => buildStrategyScenario(contract, liveMark, markets, portfolioResources),
    [contract, liveMark, markets, portfolioResources],
  );'''

ROUTE_RECOMMENDATION_PATTERN = re.compile(
    r'''  const routeRecommendationRequest = useMemo\(\(\) => \(\{\n[\s\S]*?\n  \}\), \[portfolioResources, saleOptions, totalPoolVolume, upstreamContracts\]\);'''
)

ROUTE_RECOMMENDATION_REPLACEMENT = '''  const routeRecommendationRequest = useMemo(
    () => buildRouteRecommendationRequest(portfolioResources, saleOptions, totalPoolVolume, upstreamContracts),
    [portfolioResources, saleOptions, totalPoolVolume, upstreamContracts],
  );'''


def _read_preserving_bom(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    return raw.decode("utf-8-sig"), has_bom


def _write_preserving_bom(path: Path, text: str, has_bom: bool) -> None:
    payload = text.encode("utf-8")
    if has_bom:
        payload = codecs.BOM_UTF8 + payload
    path.write_bytes(payload)


def _insert_import(text: str) -> str:
    if APP_IMPORT in text:
        return text
    if IMPORT_ANCHOR not in text:
        raise RuntimeError("WorkspaceTopBar import anchor not found; refusing to edit App.tsx")
    return text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + APP_IMPORT, 1)


def _replace_once(pattern: re.Pattern[str], replacement: str, text: str, label: str) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Expected exactly one {label} block, found {count}; refusing to edit App.tsx")
    return updated


def main() -> int:
    text, has_bom = _read_preserving_bom(APP_TSX)
    original = text

    text = _insert_import(text)
    text = _replace_once(RESOURCE_POOL_PATTERN, RESOURCE_POOL_REPLACEMENT, text, "resource pool request")
    text = _replace_once(CONTRACT_PAYLOAD_PATTERN, CONTRACT_PAYLOAD_REPLACEMENT, text, "contract payload")
    text = _replace_once(STRATEGY_SCENARIO_PATTERN, STRATEGY_SCENARIO_REPLACEMENT, text, "strategy scenario")
    text = _replace_once(ROUTE_RECOMMENDATION_PATTERN, ROUTE_RECOMMENDATION_REPLACEMENT, text, "route recommendation request")

    if "research_only" in text:
        raise RuntimeError("Legacy research_only payload flag is still present after wiring; refusing to write")
    for required in [
        "buildContractPayload(contract)",
        "buildResourcePoolOptimizationRequest(contract, portfolioResources, saleOptions, upstreamContracts)",
        "buildRouteRecommendationRequest(portfolioResources, saleOptions, totalPoolVolume, upstreamContracts)",
        "buildStrategyScenario(contract, liveMark, markets, portfolioResources)",
    ]:
        if required not in text:
            raise RuntimeError(f"Expected wired builder call missing: {required}")

    if text == original:
        print("App.tsx already wired; no changes needed.")
        return 0

    _write_preserving_bom(APP_TSX, text, has_bom)
    print("App.tsx wired to extracted builders.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
