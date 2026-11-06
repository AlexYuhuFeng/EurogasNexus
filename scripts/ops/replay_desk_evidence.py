"""Replay normalized desk evidence without connecting to a deployment."""

import argparse
import json
from pathlib import Path

from eurogas_nexus.domain.portfolio.desk_replay import DeskReplay, replay


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = replay(DeskReplay.model_validate_json(args.input.read_bytes()))
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
