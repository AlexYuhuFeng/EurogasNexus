"""Corporate proxy and CA bundle for connectors that do not trust the environment."""

from eurogas_nexus.core.outbound_http import client_options


def test_proxy_and_bundle_are_passed_and_no_proxy_is_honoured(tmp_path):
    bundle = tmp_path / "corp.pem"
    bundle.write_text("x")
    env = {
        "HTTPS_PROXY": "http://proxy.corp:8080",
        "NO_PROXY": "localhost,.internal",
        "SSL_CERT_FILE": str(bundle),
    }
    assert client_options("https://data.nationalgas.com/x", env) == {
        "proxy": "http://proxy.corp:8080",
        "verify": str(bundle),
    }
    assert "proxy" not in client_options("https://api.firm.internal/x", env)
    assert client_options("https://x.example", {}) == {}
    assert client_options("https://x.example", {"SSL_CERT_FILE": "/missing.pem"}) == {}
