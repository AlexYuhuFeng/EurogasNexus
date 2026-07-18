"""Architecture contracts for DB-owned intraday decision support."""

from pathlib import Path

from eurogas_nexus.db.registry import list_required_tables

ROOT = Path(__file__).resolve().parents[2]


def test_intraday_runtime_tables_and_migration_are_registered() -> None:
    required = set(list_required_tables())
    migration = (
        ROOT / "alembic" / "versions" / "0014_intraday_decision_feed.py"
    ).read_text(encoding="utf-8")

    assert {
        "market_quotes",
        "company_tso_access",
        "intraday_opportunities",
    }.issubset(required)
    assert 'revision: str = "0014_intraday_decision_feed"' in migration
    assert 'down_revision: str | None = "0013_gie_lng_dtmi_energy"' in migration


def test_intraday_api_and_sdk_use_stable_unversioned_paths() -> None:
    api_route = (
        ROOT
        / "src"
        / "eurogas_nexus"
        / "api"
        / "routes"
        / "public"
        / "market.py"
    ).read_text(encoding="utf-8")
    sdk = (
        ROOT / "src" / "eurogas_nexus" / "sdk" / "market.py"
    ).read_text(encoding="utf-8")

    assert '"/api/market/quotes"' in api_route
    assert '"/api/market/opportunities"' in api_route
    assert 'api_url(base_url, "market/quotes")' in sdk
    assert 'api_url(base_url, "market/opportunities")' in sdk
    assert "/api/v1" not in api_route + sdk
    assert "/v1" not in api_route + sdk


def test_web_refreshes_db_backed_decisions_every_ten_seconds() -> None:
    hook = (
        ROOT
        / "clients"
        / "web"
        / "src"
        / "app"
        / "hooks"
        / "useWorkspaceRuntime.ts"
    ).read_text(encoding="utf-8")
    api_client = (
        ROOT / "clients" / "web" / "src" / "api" / "client.ts"
    ).read_text(encoding="utf-8")
    feed = (
        ROOT
        / "clients"
        / "web"
        / "src"
        / "components"
        / "IntradayDecisionFeed.tsx"
    ).read_text(encoding="utf-8")

    assert "MARKET_REFRESH_INTERVAL_MS = 10_000" in hook
    assert "setInterval" in hook
    assert 'get<MarketQuoteDTO[]>("/market/quotes"' in api_client
    assert 'get<IntradayOpportunityDTO[]>("/market/opportunities"' in api_client
    assert "gross_spread =" not in feed
    assert "net_margin =" not in feed
    assert "postgres" not in feed.lower()

    store = (
        ROOT / "clients" / "web" / "src" / "stores" / "api.ts"
    ).read_text(encoding="utf-8")
    assert "marketQuotes: []," in store
    assert "intradayOpportunities: []," in store
