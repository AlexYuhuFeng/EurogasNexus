"""Eurogas Nexus CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable

from eurogas_nexus.cli import commands

CommandHandler = Callable[[str, argparse.Namespace], object]

# Exit codes: 0 success, 1 BLOCKED outcome (decision support failed closed),
# 2 unexpected failure (network/API errors raised by the command).
EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_ERROR = 2


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse arguments and dispatch to SDK-backed commands.

    Args:
        argv: Argument list; None uses ``sys.argv[1:]``.

    Returns:
        Process exit code: 0 success, 1 runtime failure, 2 usage error.
    """

    parser = argparse.ArgumentParser(prog="eurogas-nexus")
    parser.add_argument("--base-url", default="http://localhost:8000")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_simple(subparsers, "health", _health)
    _add_simple(subparsers, "runtime-db", _runtime_db)
    _add_simple(subparsers, "nodes", _nodes)
    _add_simple(subparsers, "routes", _routes)
    _add_simple(subparsers, "capacity-contracts", _capacity_contracts)
    _add_simple(subparsers, "hdd-cdd", _hdd_cdd)
    _add_simple(subparsers, "strategy-runs", _strategy_runs)
    _add_simple(subparsers, "strategy-summary", _strategy_summary)
    _add_simple(subparsers, "sources", _sources)
    _add_simple(subparsers, "market", _market)
    _add_simple(subparsers, "fx", _fx)
    _add_simple(subparsers, "flows", _flows)
    _add_simple(subparsers, "credential-providers", _credential_providers)
    _add_simple(subparsers, "review-decisions", _review_decisions)
    _add_optimize(subparsers)
    _add_optimization_run(subparsers)
    _add_analyze(subparsers)

    args = parser.parse_args(argv)
    handler: CommandHandler = args.handler
    try:
        result = handler(args.base_url, args)
    except Exception as exc:  # network/API failures must not exit 0
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    print(_serialize(result))
    return _exit_code_for_result(result)


def _add_simple(subparsers: argparse._SubParsersAction, name: str, handler: CommandHandler) -> None:
    parser = subparsers.add_parser(name)
    parser.set_defaults(handler=handler)


def _health(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_health(base_url)


def _runtime_db(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_runtime_db(base_url)


def _nodes(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_nodes(base_url)


def _routes(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_route_eligibility(base_url)


def _capacity_contracts(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_capacity_contracts(base_url)


def _hdd_cdd(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_hdd_cdd(base_url)


def _strategy_runs(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_strategy_runs(base_url)


def _strategy_summary(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_strategy_summary(base_url)


def _sources(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_sources(base_url)


def _market(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_market(base_url)


def _fx(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_fx(base_url)


def _flows(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_flows(base_url)


def _credential_providers(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_credential_providers(base_url)


def _review_decisions(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_review_decisions(base_url)


def _add_optimize(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "optimize", help="Run a sandbox optimization from a JSON request file."
    )
    parser.add_argument(
        "--kind",
        required=True,
        choices=list(commands.OPTIMIZATION_KINDS),
        help="Optimization kind.",
    )
    parser.add_argument("--input", required=True, help="JSON request file.")
    parser.set_defaults(handler=_optimize)


def _optimize(base_url: str, args: argparse.Namespace) -> object:
    return commands.cmd_optimize(base_url, kind=args.kind, input_path=args.input)


def _add_optimization_run(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "optimization-run", help="Read one persisted optimization run (evidence)."
    )
    parser.add_argument("run_id")
    parser.set_defaults(handler=_optimization_run)


def _optimization_run(base_url: str, args: argparse.Namespace) -> object:
    return commands.cmd_optimization_run(base_url, args.run_id)


def _add_analyze(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("analyze", help="Run a governed analysis query.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--task", default="DB_INQUIRY")
    parser.add_argument("--invoke-provider", action="store_true")
    parser.set_defaults(handler=_analyze)


def _analyze(base_url: str, args: argparse.Namespace) -> object:
    return commands.cmd_analyze(
        base_url,
        question=args.question,
        task=args.task,
        invoke_provider=args.invoke_provider,
    )


def _serialize(result: object) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, list):
        return json.dumps(
            [item.model_dump() if hasattr(item, "model_dump") else item for item in result],
            indent=2,
            default=str,
        )
    if hasattr(result, "model_dump"):
        return json.dumps(result.model_dump(), indent=2, default=str)
    return json.dumps(result, indent=2, default=str)


def _status_of_result(result: object) -> str | None:
    """Extract an outcome status from command results (envelope or model)."""

    if hasattr(result, "status"):
        return str(result.status).upper()
    if isinstance(result, dict):
        data = result.get("data") if "data" in result else result
        if isinstance(data, dict) and isinstance(data.get("status"), str):
            return data["status"].upper()
        meta = result.get("meta") if isinstance(result, dict) else None
        if isinstance(meta, dict) and isinstance(meta.get("status"), str):
            return meta["status"].upper()
    return None


def _exit_code_for_result(result: object) -> int:
    """Map command outcomes onto exit codes (BLOCKED/infeasible -> non-zero)."""

    if _status_of_result(result) in {"BLOCKED", "INFEASIBLE"}:
        return EXIT_BLOCKED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
