"""Release smoke must use named authorization without disclosing credentials."""

import json
import runpy
from pathlib import Path

import httpx
import pytest


@pytest.mark.parametrize("denied", [False, True])
def test_release_smoke_forwards_named_identity_and_preserves_denial(monkeypatch, capsys, denied):
    script = Path(__file__).resolve().parents[2] / "scripts/release/smoke_release.py"
    main = runpy.run_path(str(script))["main"]
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "synthetic-deployment-secret")
    monkeypatch.setenv("EUROGAS_NEXUS_IDENTITY_BEARER", "synthetic-identity-secret")
    seen = []

    def handle(request):
        assert request.headers["X-Eurogas-Api-Key"] == "synthetic-deployment-secret"
        assert request.headers["X-Eurogas-Identity"] == "synthetic-identity-secret"
        seen.append(request.url.path)
        return httpx.Response(403 if denied and request.url.path.endswith("strategy-runs") else 200)

    client_type = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: client_type(transport=httpx.MockTransport(handle), **kw)
    )
    assert main(["--base-url", "http://release.test/api", "--json"]) == int(denied)
    output = capsys.readouterr().out
    assert "synthetic-deployment-secret" not in output
    assert "synthetic-identity-secret" not in output
    report = json.loads(output)
    assert report["ok"] is not denied
    assert len(seen) == 8
    if denied:
        assert (
            next(row for row in report["results"] if row["check"] == "strategy_runs")["ok"] is False
        )
