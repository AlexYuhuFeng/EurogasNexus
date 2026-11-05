"""Thin CLI adapter for functional API tasks and research model operations."""

import json
from pathlib import Path

from eurogas_nexus_sdk.functional import OPERATIONS, operate


def register(subparsers):
    parser = subparsers.add_parser(
        "functional", help="Submit, inspect and replay functional tasks."
    )
    parser.add_argument("operation", choices=tuple(OPERATIONS))
    parser.add_argument("--id", dest="identifier")
    parser.add_argument("--input", help="JSON request file for the selected operation.")
    parser.set_defaults(handler=run)


def run(base_url, args):
    body = None
    if args.input:
        path = Path(args.input)
        if path.stat().st_size > 2_000_000:
            raise ValueError("functional request exceeds 2 MB")
        body = json.loads(path.read_text(encoding="utf-8"))
    return operate(base_url, args.operation, identifier=args.identifier, body=body)
