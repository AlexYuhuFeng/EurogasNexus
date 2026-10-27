#!/usr/bin/env python
"""Compare local LNG terminal-source bytes with the committed reference manifest.

This is an offline, bounded inspection. It reads only the manifest and candidate
files named on the command line, prints JSON, and performs no network, database,
source activation, grant or manifest write.

Exit codes:
    0  candidate bytes match the preserved source hash
    1  malformed input, unsafe/unreadable file, unknown source or invalid time
    2  bytes changed; review is required and no automatic replacement occurred
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from eurogas_nexus.domain.route_cost.lng_terminal_reference import (  # noqa: E402
    LngReferenceErrorCode,
    LngTerminalReferenceError,
    SourceChangeStatus,
    compare_lng_terminal_source_bytes,
    load_lng_terminal_reference_manifest,
    parse_retrieved_at_utc,
    read_lng_terminal_candidate_file,
)


class _JsonArgumentParser(argparse.ArgumentParser):
    """Turn argparse refusals into the same bounded JSON error envelope."""

    def error(self, message: str) -> NoReturn:
        raise LngTerminalReferenceError(
            LngReferenceErrorCode.CLI_ARGUMENT_INVALID,
            message,
        )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = _JsonArgumentParser(
        description=(
            "Compare one bounded local candidate file with the preserved source hash "
            "in the LNG terminal-reference manifest. No file is written."
        )
    )
    parser.add_argument(
        "--manifest",
        required=True,
        type=Path,
        help="local UTF-8 JSON terminal-reference manifest",
    )
    parser.add_argument(
        "--source-id",
        required=True,
        help="source_id already present in the manifest",
    )
    parser.add_argument(
        "--candidate-file",
        required=True,
        type=Path,
        help="local candidate bytes to hash and compare",
    )
    parser.add_argument(
        "--retrieved-at",
        required=True,
        help="explicit ISO-8601 UTC retrieval time, for example 2026-10-27T12:00:00Z",
    )
    return parser.parse_args(argv)


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _error_payload(code: str, message: str) -> dict[str, object]:
    return {
        "status": "ERROR",
        "error_code": code,
        "message": message,
        "auto_replace": False,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the offline comparison and return 0, 1 or 2 as documented."""

    try:
        args = _parse_args(argv)
        retrieved_at = parse_retrieved_at_utc(args.retrieved_at)
        manifest = load_lng_terminal_reference_manifest(args.manifest)
        candidate_bytes = read_lng_terminal_candidate_file(args.candidate_file)
        result = compare_lng_terminal_source_bytes(
            manifest,
            source_id=args.source_id,
            candidate_bytes=candidate_bytes,
            retrieved_at_utc=retrieved_at,
        )
    except LngTerminalReferenceError as exc:
        _print_json(_error_payload(exc.code, exc.message))
        return 1
    except Exception:
        # Deliberately no traceback or raw input in operator output. The generic
        # refusal still has a stable code and cannot be mistaken for review-required.
        _print_json(
            _error_payload(
                LngReferenceErrorCode.INTERNAL_ERROR.value,
                "comparison could not be completed safely",
            )
        )
        return 1

    _print_json(result.model_dump(mode="json"))
    if result.status is SourceChangeStatus.REVIEW_REQUIRED:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
