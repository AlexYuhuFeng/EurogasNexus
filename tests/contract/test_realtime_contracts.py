"""Near-real-time SSE delivery contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "clients" / "web" / "src"


def test_web_client_streams_via_event_source_with_polling_fallback() -> None:
    client = (WEB / "api" / "client.ts").read_text(encoding="utf-8")
    store = (WEB / "stores" / "api.ts").read_text(encoding="utf-8")
    live = (WEB / "app" / "data" / "liveStream.ts").read_text(encoding="utf-8")
    runtime = (WEB / "app" / "hooks" / "useWorkspaceRuntime.ts").read_text(encoding="utf-8")
    assert "openEventStream" in client
    assert "new EventSource" in client
    assert "subscribeDecisionStreams" in store
    # ONE multiplexed stream per browser tab (the per-person stream cap counts tabs): the
    # per-feed streams are not opened by the web client.
    assert "/stream/live?" in live and "LIVE_TAB_TOPICS" in live
    for feed in ("/stream/quotes", "/stream/opportunities", "/stream/alerts"):
        assert feed not in store and feed not in live
    assert "streamingActive" in runtime
    # polling remains as the fallback transport
    assert "MARKET_REFRESH_INTERVAL_MS" in runtime


def test_pipeline_health_routes_are_registered() -> None:
    from apps.api.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/runtime/pipeline-health" in paths
