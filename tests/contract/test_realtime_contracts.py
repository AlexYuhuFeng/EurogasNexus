"""Near-real-time SSE delivery contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "clients" / "web" / "src"


def test_web_client_streams_via_event_source_with_polling_fallback() -> None:
    client = (WEB / "api" / "client.ts").read_text(encoding="utf-8")
    store = (WEB / "stores" / "api.ts").read_text(encoding="utf-8")
    runtime = (WEB / "app" / "hooks" / "useWorkspaceRuntime.ts").read_text(encoding="utf-8")
    assert "openEventStream" in client
    assert "new EventSource" in client
    assert "subscribeDecisionStreams" in store
    assert "/stream/quotes" in store
    assert "/stream/opportunities" in store
    assert "/stream/alerts" in store
    assert "streamingActive" in runtime
    # polling remains as the fallback transport
    assert "MARKET_REFRESH_INTERVAL_MS" in runtime


def test_strategy_bar_minutes_is_operator_selectable() -> None:
    """The bar size is a declared scenario input.

    This contract used to assert a `"1" | "5" | "15"` selector in
    `StrategyShadowRunTerminal.tsx`. That component was never mounted - nothing rendered it, so no
    operator could ever select a bar size - and the owner retired it in favour of the shadow task's
    two halves (monitor management, and what the run's economics rest on). What is asserted here is
    what the product actually does: the scenario builder declares the bar size the runs are built
    with, and the portfolio's decision model carries its own target. An operator-selectable control
    for it does not exist today, and that is recorded as a gap rather than claimed as a feature.
    """
    scenario = (WEB / "app" / "strategyScenario.ts").read_text(encoding="utf-8")
    portfolio = (WEB / "app" / "model" / "usePortfolioDecisionModel.ts").read_text(
        encoding="utf-8"
    )

    assert "bar_minutes" in scenario
    assert "target_bar_minutes" in portfolio
    assert "bar_minutes: 5" in scenario
    # The retired terminal is gone, so the previous claim cannot be read as current state.
    assert not (WEB / "components" / "StrategyShadowRunTerminal.tsx").exists()


def test_pipeline_health_routes_are_registered() -> None:
    from apps.api.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/runtime/pipeline-health" in paths
