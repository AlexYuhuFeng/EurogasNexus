"""CLI entrypoint tests."""

from types import SimpleNamespace

import pytest

from eurogas_nexus.cli.main import main


def test_cli_main_health_command(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "eurogas_nexus.cli.main.commands.cmd_health",
        lambda base_url: f"status=ok base={base_url}",
    )

    result = main(["--base-url", "http://example.test", "health"])

    assert result == 0
    assert "status=ok base=http://example.test" in capsys.readouterr().out


def test_cli_main_nodes_command_outputs_json(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "eurogas_nexus.cli.main.commands.cmd_nodes",
        lambda base_url: [{"id": "node-test"}],
    )

    result = main(["nodes"])

    assert result == 0
    assert '"id": "node-test"' in capsys.readouterr().out


def test_cli_rejects_removed_workflow_shell_commands() -> None:
    for command in ("route-cost", "shadow-run", "brief"):
        with pytest.raises(SystemExit) as exc_info:
            main([command])
        assert exc_info.value.code == 2


def test_cli_optimize_runs_from_json_file(monkeypatch, capsys, tmp_path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text(
        '{"resources": [], "sale_options": [], "decision_context": "SANDBOX_SCENARIO"}',
        encoding="utf-8",
    )

    def fake_optimize(base_url, **kwargs):
        return SimpleNamespace(
            data=SimpleNamespace(
                model_dump=lambda: {"status": "optimal", "objective_value_gbp": 100.0}
            )
        )

    monkeypatch.setattr(
        "eurogas_nexus.cli.main.commands.optimize_resource_pool",
        fake_optimize,
    )

    result = main(["optimize", "--kind", "resource-pool", "--input", str(request_file)])

    assert result == 0
    assert '"status": "optimal"' in capsys.readouterr().out


def test_cli_optimization_run_reads_evidence(monkeypatch, capsys) -> None:
    def fake_run(base_url, run_id):
        return SimpleNamespace(
            data=SimpleNamespace(
                model_dump=lambda: {
                    "run_id": run_id,
                    "optimization_type": "resource_pool",
                    "decision_context": "RUNTIME_DECISION",
                    "status": "SUCCESS",
                    "input_snapshot": {},
                    "output_snapshot": {},
                    "source_refs": [],
                    "warnings": [],
                    "created_at_utc": "2026-07-01T12:00:00+00:00",
                    "research_only": True,
                    "human_review_required": True,
                }
            )
        )

    monkeypatch.setattr(
        "eurogas_nexus.cli.main.commands.fetch_optimization_run",
        fake_run,
    )

    result = main(["optimization-run", "opt-abc"])

    assert result == 0
    assert '"run_id": "opt-abc"' in capsys.readouterr().out


def test_cli_optimize_exits_1_on_infeasible(monkeypatch, tmp_path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")

    def fake_optimize(base_url, **kwargs):
        return SimpleNamespace(
            data=SimpleNamespace(model_dump=lambda: {"status": "infeasible"})
        )

    monkeypatch.setattr(
        "eurogas_nexus.cli.main.commands.optimize_contracts",
        fake_optimize,
    )

    result = main(["optimize", "--kind", "contracts", "--input", str(request_file)])

    assert result == 1


def test_cli_analyze_runs_governed_query(monkeypatch, capsys) -> None:
    def fake_ask(base_url, **kwargs):
        assert kwargs["question"] == "Summarize TTF"
        return SimpleNamespace(
            model_dump=lambda: {
                "analysis_id": "a1",
                "task": "DB_INQUIRY",
                "provider_status": "not_invoked",
                "warnings": [],
            }
        )

    monkeypatch.setattr("eurogas_nexus.cli.main.commands.ask_analysis", fake_ask)

    result = main(["analyze", "--question", "Summarize TTF"])

    assert result == 0
    assert '"provider_status": "not_invoked"' in capsys.readouterr().out
