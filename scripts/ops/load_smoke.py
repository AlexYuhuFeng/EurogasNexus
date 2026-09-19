"""In-process API load smoke (no server, no network).

Runs concurrent GETs against the FastAPI app via httpx's ASGI transport and
reports latency percentiles. Gate-4 load baseline: catches pathological
latency/error regressions in CI without standing up a server.

Usage:
    python scripts/ops/load_smoke.py [--requests N] [--concurrency C]
        [--p95-threshold-ms 500] [--error-rate-threshold 0.05]
        [--base-url http://127.0.0.1:8765]

Without ``--base-url`` the smoke drives the in-process ASGI app. With it, the
same workload goes over real HTTP to a running server, which additionally
exercises the served stack (uvicorn, sockets, middleware order) that the
in-process transport cannot reach. `scripts/ops/run_served_load_smoke.sh`
starts such a server for CI.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import sys
import time
from collections.abc import Callable
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
for import_path in (ROOT, SRC):
    if str(import_path) not in sys.path:
        sys.path.insert(0, str(import_path))

SMOKE_PATHS = (
    "/api/health",
    "/api/sources",
    "/api/reference-network/market-hubs",
    "/api/route-cost/tso-tariffs",
    "/api/market/fx",
)


def _app_transport():
    from httpx import ASGITransport

    from apps.api.main import app

    return ASGITransport(app=app)


def run_requests(
    total: int,
    concurrency: int,
    paths: tuple[str, ...],
    *,
    transport: Callable[[], httpx.ASGITransport] = _app_transport,
    base_url: str | None = None,
) -> tuple[list[float], list[str]]:
    """Fire ``total`` GETs across the smoke paths; return (latencies, errors).

    ``base_url`` selects a real HTTP target and bypasses the in-process
    transport. When it is omitted, the in-process behavior is unchanged.
    """

    async def runner() -> tuple[list[float], list[str]]:
        semaphore = asyncio.Semaphore(concurrency)
        latencies: list[float] = []
        errors: list[str] = []
        lock = asyncio.Lock()

        async def one(index: int) -> None:
            async with semaphore:
                client = httpx.AsyncClient(
                    transport=None if base_url else transport(),
                    base_url=base_url or "http://loadtest.local",
                    timeout=30.0,
                    headers=_caller_headers(),
                )
                try:
                    path = paths[index % len(paths)]
                    started = time.perf_counter()
                    try:
                        response = await client.get(path)
                        elapsed_ms = (time.perf_counter() - started) * 1000.0
                        if response.status_code >= 400:
                            # Owner decision D1: a caller that presents nothing is refused, so a
                            # 401 measured as a healthy latency would hide exactly the failure this
                            # smoke exists to catch.
                            async with lock:
                                errors.append(f"{path}:{response.status_code}")
                        else:
                            async with lock:
                                latencies.append(elapsed_ms)
                    except httpx.HTTPError as exc:
                        async with lock:
                            errors.append(f"{path}:{exc.__class__.__name__}")
                finally:
                    await client.aclose()

        await asyncio.gather(*(one(index) for index in range(total)))
        return latencies, errors

    return asyncio.run(runner())


def _caller_headers() -> dict[str, str]:
    """The credential this smoke presents, or a refusal to run without one.

    The in-process target is the real ASGI app, and since owner decision D1 it identifies its
    callers in every profile. The smoke acts as the documented SDK/CLI caller (deployment token from
    the environment), and refuses to produce a baseline that would only measure refusals.
    """

    token = os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "").strip()
    if token:
        return {"X-Eurogas-Api-Key": token}
    if os.environ.get("EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS", "").strip() in {"1", "true", "yes"}:
        return {}
    raise SystemExit(
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN is not set and this deployment does not allow anonymous "
        "callers: every smoke path would answer 401. Set the token, or set "
        "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS=1 if the deployment really does trust its network."
    )


def percentile(values: list[float], pct: float) -> float:
    """    Nearest-rank percentile of a list (0.0 for an empty list)."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[index]


def main(argv: list[str] | None = None) -> int:
    """    Run the load smoke test against the API."""
    args = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument("--p95-threshold-ms", type=float, default=500.0)
    parser.add_argument("--error-rate-threshold", type=float, default=0.05)
    parser.add_argument(
        "--base-url",
        default=None,
        help="Target a running server over real HTTP instead of the in-process ASGI app.",
    )
    parsed = parser.parse_args(args)

    started = time.perf_counter()
    latencies, errors = run_requests(
        parsed.requests,
        parsed.concurrency,
        SMOKE_PATHS,
        base_url=parsed.base_url,
    )
    elapsed_s = time.perf_counter() - started
    error_rate = len(errors) / parsed.requests if parsed.requests else 0.0
    p95 = percentile(latencies, 0.95)
    p99 = percentile(latencies, 0.99)

    print(
        f"load smoke: {len(latencies)} ok / {len(errors)} errors "
        f"in {elapsed_s:.1f}s (concurrency={parsed.concurrency}, "
        f"target={parsed.base_url or 'in-process ASGI'})"
    )
    if latencies:
        print(
            f"latency ms: p50={percentile(latencies, 0.5):.1f} "
            f"p95={p95:.1f} p99={p99:.1f} max={max(latencies):.1f} "
            f"mean={statistics.mean(latencies):.1f}"
        )
    if errors:
        print("errors: " + "; ".join(dict.fromkeys(errors)[:8]))
    failed = error_rate > parsed.error_rate_threshold or p95 > parsed.p95_threshold_ms
    if failed:
        print(
            f"load smoke FAILED: error_rate={error_rate:.3f} "
            f"(>{parsed.error_rate_threshold}) or p95={p95:.1f}ms "
            f"(>{parsed.p95_threshold_ms}ms)"
        )
        return 1
    print("load smoke OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
