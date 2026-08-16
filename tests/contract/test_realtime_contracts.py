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
    terminal = (
        WEB / "components" / "StrategyShadowRunTerminal.tsx"
    ).read_text(encoding="utf-8")
    renderer = (WEB / "app" / "workspaces" / "WorkspaceRenderer.tsx").read_text(
        encoding="utf-8"
    )

    assert "bar_minutes" in terminal
    assert "target_bar_minutes" in renderer
    assert '"1", "5", "15"' in terminal


def test_pipeline_health_routes_are_registered() -> None:
    from apps.api.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/runtime/pipeline-health" in paths
