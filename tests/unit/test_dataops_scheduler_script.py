"""CR-09 scheduler script tests (no live provider calls)."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from eurogas_nexus.domain.dataops.contracts import FailureCategory
from scripts.ops.run_dataops_scheduler import (
    _SOURCE_ARGS,
    run_ingestor_attempt,
    run_loop,
)


def test_scheduler_maps_only_implemented_public_sources() -> None:
    assert set(_SOURCE_ARGS) == {"src-ecb", "src-entsog", "src-gie"}
    assert _SOURCE_ARGS["src-ecb"] == ("ecb",)


def test_ingestor_attempt_parses_success_report() -> None:
    def fake_runner(command, **kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "sources": {"ECB": {"records": 12}}}),
            stderr="",
        )

    attempt = run_ingestor_attempt(fake_runner)
    result = attempt({"source_id": "src-ecb", "run_id": "run-1"}, 1)

    assert result.succeeded is True
    assert result.rows_received == 12
    assert result.lineage_refs == ["public-source-ingestor:src-ecb"]


def test_ingestor_attempt_classifies_unsupported_source_as_configuration() -> None:
    attempt = run_ingestor_attempt(subprocess.run)
    result = attempt({"source_id": "src-platts", "run_id": "run-1"}, 1)

    assert result.succeeded is False
    assert result.classification == FailureCategory.CONFIGURATION


def test_ingestor_attempt_classifies_bad_json_as_bad_response() -> None:
    def fake_runner(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="not-json", stderr="")

    result = run_ingestor_attempt(fake_runner)(
        {"source_id": "src-ecb", "run_id": "run-1"}, 1
    )

    assert result.succeeded is False
    assert result.classification == FailureCategory.BAD_RESPONSE


def test_run_loop_blocks_without_database(monkeypatch, capsys) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    result = run_loop(
        interval_seconds=1,
        max_iterations=1,
        emit=lambda value: None,
    )

    assert result == 2
    captured = capsys.readouterr()
    assert "database_url_missing" not in captured.out  # emit was suppressed
