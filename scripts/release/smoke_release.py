"""Post-deployment release smoke check.

Verifies critical platform surfaces without invoking external commercial
providers. Exits non-zero on any critical failure.

Usage:
    python scripts/release/smoke_release.py --base-url http://127.0.0.1:8000/api
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx

CRITICAL_PATHS = (
    ("liveness", "/health/live", 200),
    ("readiness", "/health/ready", 200),
    ("runtime_db", "/runtime/db", 200),
    ("runtime_release", "/runtime/release", 200),
    ("sources", "/sources", 200),
    ("strategy_runs", "/strategy-runs?limit=5", 200),
    ("route_candidates", "/route-cost/route-candidates", 200),
    ("source_operations", "/runtime/source-operations", 200),
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.environ.get("EUROGAS_NEXUS_RELEASE_BASE_URL", "http://127.0.0.1:8000/api"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    base = args.base_url.rstrip("/")
    token = os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "").strip()
    headers = {"X-Eurogas-Api-Key": token} if token else {}
    results = []
    critical_failures = []
    with httpx.Client(timeout=args.timeout_seconds) as client:
        for name, path, expected in CRITICAL_PATHS:
            try:
                response = client.get(f"{base}{path}", headers=headers)
                ok = response.status_code == expected
                results.append(
                    {
                        "check": name,
                        "status_code": response.status_code,
                        "ok": ok,
                    }
                )
                if not ok:
                    critical_failures.append(name)
            except Exception as exc:
                results.append({"check": name, "ok": False, "error": exc.__class__.__name__})
                critical_failures.append(name)

    report = {"ok": not critical_failures, "results": results}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for row in results:
            state = "ok" if row.get("ok") else "FAILED"
            detail = row.get("status_code") or row.get("error") or ""
            print(f"{row['check']}: {state} {detail}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
