"""CR-11 performance baseline harness.

Runs representative interactive API workloads against the in-process ASGI app
(optionally with the configured PostgreSQL store) and records p50/p95/p99,
errors, row-count context and methodology. No fragile microbenchmark gate.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

BASELINE_PATHS = (
    "/api/health/live",
    "/api/sources",
    "/api/reference-network/market-hubs?limit=200",
    "/api/market/quotes?limit=100",
    "/api/route-cost/route-candidates",
    "/api/strategy-runs?limit=20",
    "/api/runtime/pipeline-health",
    "/api/runtime/source-operations",
)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * pct))]


def _caller_headers() -> dict[str, str]:
    """The credential this harness presents, or a refusal to run without one.

    Owner decision D1 installs authentication in every profile, so the ASGI app this harness drives
    refuses a request that presents nothing: a baseline measured without a credential would be a
    table of 401 latencies. The harness therefore acts as the documented SDK/CLI caller, with the
    deployment token from the environment. A deployment that explicitly permits anonymous callers
    does not need one, and the harness says which of the two it is in its report.
    """

    import os

    token = os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "").strip()
    if token:
        return {"X-Eurogas-Api-Key": token}
    if os.environ.get("EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS", "").strip() in {"1", "true", "yes"}:
        return {}
    raise SystemExit(
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN is not set and this deployment does not allow anonymous "
        "callers: every measured path would answer 401. Set the token, or set "
        "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS=1 if the deployment really does trust its network."
    )


def run_baseline(total: int, concurrency: int) -> tuple[list[float], list[str]]:
    from apps.api.main import app

    transport = httpx.ASGITransport(app=app)
    headers = _caller_headers()

    async def runner() -> tuple[list[float], list[str]]:
        semaphore = asyncio.Semaphore(concurrency)
        latencies: list[float] = []
        errors: list[str] = []
        lock = asyncio.Lock()

        async def one(index: int) -> None:
            async with semaphore:
                client = httpx.AsyncClient(transport=transport, timeout=30.0)
                try:
                    url = "http://baseline.local" + BASELINE_PATHS[index % len(BASELINE_PATHS)]
                    started = time.perf_counter()
                    try:
                        response = await client.get(url, headers=headers)
                        elapsed = (time.perf_counter() - started) * 1000.0
                        if response.status_code >= 400:
                            # An authenticated caller should not see 4xx either: counting only 5xx
                            # hid a refusal behind a healthy-looking latency.
                            async with lock:
                                errors.append(f"{url}:{response.status_code}")
                        else:
                            async with lock:
                                latencies.append(elapsed)
                    except httpx.HTTPError as exc:
                        async with lock:
                            errors.append(f"{url}:{exc.__class__.__name__}")
                finally:
                    await client.aclose()

        await asyncio.gather(*(one(index) for index in range(total)))
        return latencies, errors

    return asyncio.run(runner())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=400)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    latencies, errors = run_baseline(args.requests, args.concurrency)
    elapsed_s = time.perf_counter() - started
    report = {
        "methodology": {
            "harness": "in-process ASGI",
            "concurrency": args.concurrency,
            "requests": args.requests,
            "paths": list(BASELINE_PATHS),
            "database_configured": bool(__import__("os").environ.get("RUNTIME_STORE_DATABASE_URL")),
        },
        "latency_ms": {
            "p50": percentile(latencies, 0.5),
            "p95": percentile(latencies, 0.95),
            "p99": percentile(latencies, 0.99),
            "mean": statistics.mean(latencies) if latencies else 0.0,
        },
        "errors": len(errors),
        "error_rate": len(errors) / args.requests if args.requests else 0.0,
        "elapsed_seconds": round(elapsed_s, 3),
    }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
