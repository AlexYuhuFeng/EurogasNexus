"""Read an export with a deal format and list every row it cannot read; stores nothing.

    python scripts/ops/check_deal_format.py --format ice_deal_report --file export.csv
    python scripts/ops/check_deal_format.py --file export.csv          # which format fits?
    python scripts/ops/check_deal_format.py --list

For whoever edits a format file (``EUROGAS_NEXUS_DEAL_FORMATS_DIR``): run it after each edit
until every row reads. No database is needed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    from eurogas_nexus.domain.deals.formats import detect_format, load_formats
    from eurogas_nexus.domain.deals.parse import decode, parse_deal_file, read_table
    from eurogas_nexus.domain.deals.record import money

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--format")
    parser.add_argument("--file")
    parser.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    formats, errors = load_formats()
    for line in errors:
        print(f"FORMAT FILE PROBLEM: {line}")
    if args.list or not args.file:
        for item in formats.values():
            print(f"{item.name:20} {item.title}  [{item.source_path}]")
        return 0 if not errors else 1
    content = Path(args.file).read_bytes()
    fmt = formats.get(args.format) if args.format else None
    if fmt is None:
        for candidate in formats.values():
            headers, _rows = read_table(decode(content), candidate)
            fmt = detect_format(headers, formats)
            if fmt:
                break
    if fmt is None:
        print("No format recognises this file's headers; name one with --format.")
        return 2
    parsed = parse_deal_file(content, fmt, file_name=Path(args.file).name, book_id="check")
    print(f"Format: {fmt.name} ({fmt.title}); {parsed.rows} rows, {len(parsed.deals)} deals, "
          f"{len(parsed.problems)} unreadable")
    for deal in parsed.deals:
        print(json.dumps({"line": deal.source_line, "key": deal.deal_key, "trader": deal.trader,
                          "hub": deal.hub, "product": deal.product, "side": deal.side,
                          "volume": f"{deal.volume} {deal.volume_unit}",
                          "total_mwh": money(deal.total_mwh, 3),
                          "price": f"{deal.price} {deal.price_unit}", "status": deal.status}))
    for problem in parsed.problems:
        print(f"LINE {problem.line}: {problem.code}: {problem.message}")
    return 0 if not parsed.problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
