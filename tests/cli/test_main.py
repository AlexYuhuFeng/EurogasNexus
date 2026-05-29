"""CLI entrypoint tests."""

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
