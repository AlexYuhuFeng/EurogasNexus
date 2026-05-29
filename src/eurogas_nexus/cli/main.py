"""Eurogas Nexus CLI entrypoint."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable

from eurogas_nexus.cli import commands

CommandHandler = Callable[[str, argparse.Namespace], object]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eurogas-nexus")
    parser.add_argument("--base-url", default="http://localhost:8000")
    subparsers = parser.add_subparsers(dest="command", required=True)

    _add_simple(subparsers, "health", _health)
    _add_simple(subparsers, "runtime-db", _runtime_db)
    _add_simple(subparsers, "nodes", _nodes)
    _add_simple(subparsers, "routes", _routes)
    _add_simple(subparsers, "capacity-contracts", _capacity_contracts)
    _add_simple(subparsers, "hdd-cdd", _hdd_cdd)
    _add_simple(subparsers, "brief", _brief)
    _add_simple(subparsers, "route-cost", _route_cost)
    _add_simple(subparsers, "shadow-run", _shadow_run)

    args = parser.parse_args(argv)
    handler: CommandHandler = args.handler
    result = handler(args.base_url, args)
    print(_serialize(result))
    return 0


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


def _brief(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_brief(base_url)


def _route_cost(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_route_cost_fixture(base_url)


def _shadow_run(base_url: str, _args: argparse.Namespace) -> object:
    return commands.cmd_shadow_run_fixture(base_url)


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


if __name__ == "__main__":
    raise SystemExit(main())
