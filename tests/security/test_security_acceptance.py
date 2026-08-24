"""Security acceptance script tests (in-process, offline)."""

from __future__ import annotations

import scripts.security.run_security_acceptance as acceptance


def test_automated_security_acceptance_passes_in_current_worktree(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)

    assert acceptance.main([]) == 0
    output = capsys.readouterr().out
    assert "Automated status: PASS" in output
    assert "External review: BLOCKED" in output
    assert "private-network/VPN-only" in output


def test_automated_security_acceptance_json_reports_external_blockers(
    monkeypatch, capsys
) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_INTERNAL_API_TOKEN", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)

    assert acceptance.main(["--json"]) == 0
    payload = capsys.readouterr().out
    assert '"automated_status": "PASS"' in payload
    assert '"external_review_status": "BLOCKED"' in payload
