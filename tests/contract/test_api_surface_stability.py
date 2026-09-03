"""Public API surface stability gate (S4.1 contract evolution policy).

The stable unversioned `/api` surface is a product contract shared by Web, SDK,
CLI, Desktop, and documentation. Adding or removing a public path is a
breaking change for all five surfaces, so it must be declared here deliberately
and mirrored in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`.

Update process: edit `PINNED_PUBLIC_PATHS`, update the policy document, then
run this test and `tests/contract/test_architecture_alignment.py` (which pins
the documented route count) in the same change.
"""

from apps.api.main import app

PINNED_PUBLIC_PATHS = {
    "/api/analysis/ontology",
    "/api/analysis/query",
    "/api/contracts/capacity",
    "/api/contracts/routes",
    "/api/cost-observations/applicable",
    "/api/cost-observations/values",
    "/api/credentials/providers",
    "/api/credentials/{provider_id}",
    "/api/credentials/{provider_id}/connection-test",
    "/api/credentials/{provider_id}/local-validation",
    "/api/credentials/{provider_id}/rotate",
    "/api/credentials/{provider_id}/status",
    "/api/dev/health",
    "/api/glossary",
    "/api/glossary/{term}",
    "/api/glossary/{term}/context",
    "/api/health",
    "/api/ingestion-runs",
    "/api/lng/observations",
    "/api/lng/terminals",
    "/api/market/fx",
    "/api/market/normalized",
    "/api/market/observations",
    "/api/market/opportunities",
    "/api/market/quotes",
    "/api/market/spreads",
    "/api/monitoring/alerts",
    "/api/monitoring/alerts/{alert_id}/acknowledge",
    "/api/monitoring/alerts/{alert_id}/analysis",
    "/api/monitoring/summary",
    "/api/optimization/capacity",
    "/api/optimization/contracts",
    "/api/optimization/nomination-window",
    "/api/optimization/portfolio-network",
    "/api/optimization/resource-pool",
    "/api/optimization/storage-dispatch",
    "/api/optimization/route",
    "/api/optimization/runs/{run_id}",
    "/api/physical/capacity",
    "/api/physical/flows",
    "/api/physical/outages",
    "/api/portfolio/live-summary",
    "/api/portfolio/pnl-snapshots",
    "/api/portfolio/screen-orders",
    "/api/reference-network/edges",
    "/api/reference-network/edges/{edge_id}",
    "/api/reference-network/facilities",
    "/api/reference-network/facilities/{facility_id}",
    "/api/reference-network/market-hubs",
    "/api/reference-network/nodes",
    "/api/reference-network/nodes/{node_id}",
    "/api/reference-network/tso-access",
    "/api/reports/portfolio",
    "/api/research/allocation",
    "/api/research/backtest",
    "/api/research/feasibility",
    "/api/research/monitoring",
    "/api/research/netback",
    "/api/research/nowcast",
    "/api/research/route-cost",
    "/api/research/shadow-run",
    "/api/review/decisions",
    "/api/route-cost/calculate",
    "/api/route-cost/lng-regas/assess",
    "/api/route-cost/recommend",
    "/api/route-cost/resource-pool/optimize",
    "/api/route-cost/resource-pool/options",
    "/api/route-cost/route-candidates",
    "/api/route-cost/tso-tariffs",
    "/api/route-cost/upstream-contracts",
    "/api/runtime/db",
    "/api/runtime/pipeline-health",
    "/api/sources",
    "/api/sources/{source_id}",
    "/api/storage/observations",
    "/api/storage/sites",
    "/api/strategy-lab/evaluate",
    "/api/strategy-lab/runs",
    "/api/strategy-lab/runs/{run_id}",
    "/api/strategy-lab/summary",
    "/api/stream/alerts",
    "/api/stream/opportunities",
    "/api/stream/quotes",
    "/api/weather/hdd-cdd",
    "/api/weather/observations",
    "/api/weather/stations",
}

DECLARED_PREFIXES = ("/api/", "/api/internal/", "/api/dev/")


def _openapi_paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_public_api_surface_is_exactly_the_pinned_set() -> None:
    paths = _openapi_paths()
    added = sorted(paths - PINNED_PUBLIC_PATHS)
    removed = sorted(PINNED_PUBLIC_PATHS - paths)
    assert added == [], (
        "Public paths added without contract declaration "
        "(update PINNED_PUBLIC_PATHS and API_CONTRACT_EVOLUTION_POLICY): "
        + ", ".join(added)
    )
    assert removed == [], (
        "Public paths removed without contract declaration: " + ", ".join(removed)
    )


def test_no_versioned_path_aliases_are_served() -> None:
    for path in _openapi_paths():
        assert not path.startswith("/v1"), f"Legacy versioned alias: {path}"
        assert not path.startswith("/api/v1"), f"Legacy versioned alias: {path}"


def test_every_path_uses_a_declared_profile_prefix() -> None:
    for path in _openapi_paths():
        assert path.startswith(DECLARED_PREFIXES), f"Undeclared path prefix: {path}"
