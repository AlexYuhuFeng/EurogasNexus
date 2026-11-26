#!/usr/bin/env python
"""Load test of the desk against a running API: N signed-in users, each with several tabs.

Each user signs in through the API (``POST /api/auth/login``, a local account) and opens
``--tabs`` tabs. A tab holds one live-update stream (``GET /api/stream/live``) for the whole run,
as the web client does, and opens desk pages one after another: a page fires its reads at once
(at most ``--per-tab-concurrency`` in flight, as a browser's per-host limit allows beside the
stream), then the tab waits a think time and opens the next page. A health probe reads
``/api/health`` every second: its latency is a direct reading of how long the event loop keeps
a request waiting.

The report gives, per route group, the count and the 50th, 95th and 99th percentile latency,
errors (a 5xx, a timeout or a broken connection) and refusals (4xx); and for the streams, how
many opened, how long the first event took, how many events arrived and how many broke. It
prints a table and, with ``--json-out``, writes the figures as JSON.

The accounts are ``--username-pattern`` (``load_u01`` ... by default) with one password read
from the environment variable named by ``--password-env``; the password is never printed.
On the demo image they are created with ``EUROGAS_NEXUS_DEMO_TEST_ACCOUNTS``
(``docs/operations/API_SERVING_AND_SHARED_CACHE.md`` has the whole procedure). Sign-in is
rate limited (30 per minute per address): the script waits and retries on a 429.

Usage:
    LOAD_TEST_PASSWORD=... python scripts/ops/load_test_desk.py \\
        --base-url http://127.0.0.1:8080 --users 50 --tabs 3 --duration 120 \\
        --json-out /tmp/load.json --label "4 processes + Valkey"

Read-only: every request is a GET, apart from the sign-ins. Never point it at a production
server without the owner's approval: 50 users with 3 tabs is a real load.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

#: The pages a tab opens, in turn: the desk's first screens and their main reads.
PAGES: dict[str, tuple[str, ...]] = {
    "today": (
        "/api/me",
        "/api/desk/today",
        "/api/portfolio/position-ladder",
        "/api/portfolio/daily-balance",
        "/api/market/instruments",
    ),
    "market": (
        "/api/research/spreads/board",
        "/api/market/nwe-balance",
        "/api/fundamentals/forward-balance",
        "/api/fundamentals/storage",
    ),
    "map": (
        "/api/portfolio/map-situation",
        "/api/fundamentals/flows",
        "/api/fundamentals/lng",
        "/api/reports/catalogue",
    ),
}
#: What a tab's live stream subscribes to (the topics the desk pages show).
STREAM_TOPICS = "prices,trades,alerts,book,opportunities,outages,flows,cargoes,jobs"
#: Route groups whose 95th percentile the plan's budget (1 s) applies to.
MAIN_READS = ("desk", "portfolio", "market", "research", "fundamentals")


def route_group(path: str) -> str:
    parts = [part for part in path.split("?")[0].split("/") if part]
    return parts[1] if len(parts) > 1 else parts[0]


@dataclass
class Results:
    latencies: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    errors: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    refusals: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    statuses: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    stream_opened: int = 0
    stream_first_event: list[float] = field(default_factory=list)
    stream_events: int = 0
    stream_broken: int = 0
    stream_refused: int = 0
    sign_in_seconds: list[float] = field(default_factory=list)
    sign_in_retries: int = 0

    def record(self, group: str, seconds: float, status: int | None) -> None:
        if status is None or status >= 500:
            self.errors[group] += 1
            self.statuses[str(status or "exception")] += 1
            return
        self.statuses[str(status)] += 1
        if status >= 400:
            self.refusals[group] += 1
            return
        self.latencies[group].append(seconds)


def percentile(values: list[float], share: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(share * len(ordered) + 0.5)) - 1))
    return ordered[index]


async def sign_in(client: httpx.AsyncClient, username: str, password: str, origin: str,
                  results: Results, deadline: float) -> str:
    """Sign in and return the session token (the cookie), retrying on the rate limit."""

    wait = 2.0
    while True:
        started = time.monotonic()
        response = await client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            headers={"Origin": origin},
        )
        if response.status_code == 429 and time.monotonic() < deadline:
            results.sign_in_retries += 1
            await asyncio.sleep(wait)
            wait = min(wait * 1.5, 15.0)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"sign-in of {username} answered {response.status_code}")
        token = response.cookies.get("eurogas_session")
        if not token:
            raise RuntimeError(f"sign-in of {username} set no session cookie")
        results.sign_in_seconds.append(time.monotonic() - started)
        return token


async def read(client: httpx.AsyncClient, path: str, token: str, results: Results,
               timeout: float) -> None:
    started = time.monotonic()
    status: int | None
    try:
        response = await client.get(path, cookies={"eurogas_session": token}, timeout=timeout)
        await response.aread()
        status = response.status_code
    except (TimeoutError, httpx.HTTPError):
        status = None
    results.record(route_group(path), time.monotonic() - started, status)


async def stream(client: httpx.AsyncClient, token: str, results: Results, stop: float) -> None:
    """Hold one live stream until ``stop``; reconnect after a break, as the client does."""

    while time.monotonic() < stop:
        started = time.monotonic()
        first = True
        try:
            async with client.stream(
                "GET",
                f"/api/stream/live?topics={STREAM_TOPICS}",
                cookies={"eurogas_session": token},
                timeout=httpx.Timeout(30.0, read=60.0),
            ) as response:
                if response.status_code == 429:
                    results.stream_refused += 1
                    return
                if response.status_code != 200:
                    results.stream_broken += 1
                    await asyncio.sleep(2)
                    continue
                results.stream_opened += 1
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        if first:
                            results.stream_first_event.append(time.monotonic() - started)
                            first = False
                        results.stream_events += 1
                    if time.monotonic() >= stop:
                        return
        except (TimeoutError, httpx.HTTPError):
            if time.monotonic() < stop:
                results.stream_broken += 1
                await asyncio.sleep(2)


async def tab(client: httpx.AsyncClient, token: str, first_page: int, results: Results,
              stop: float, args: argparse.Namespace) -> None:
    pages = list(PAGES.values())
    index = first_page
    limit = asyncio.Semaphore(args.per_tab_concurrency)

    async def bounded(path: str) -> None:
        async with limit:
            await read(client, path, token, results, args.request_timeout)

    while time.monotonic() < stop:
        await asyncio.gather(*(bounded(path) for path in pages[index % len(pages)]))
        index += 1
        await asyncio.sleep(random.uniform(args.think_min, args.think_max))


async def health_probe(client: httpx.AsyncClient, results: Results, stop: float) -> None:
    while time.monotonic() < stop:
        await read(client, "/api/health", "", results, 30.0)
        await asyncio.sleep(1.0)


async def run(args: argparse.Namespace, password: str) -> Results:
    results = Results()
    limits = httpx.Limits(max_connections=None, max_keepalive_connections=None)
    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=30.0) as client:
        sign_in_deadline = time.monotonic() + args.sign_in_budget
        tokens = []
        for number in range(1, args.users + 1):
            username = args.username_pattern.format(n=number)
            tokens.append(
                await sign_in(client, username, password, args.origin, results, sign_in_deadline)
            )
        print(f"signed in {len(tokens)} users", file=sys.stderr, flush=True)
        stop = time.monotonic() + args.duration
        tasks = [asyncio.create_task(health_probe(client, results, stop))]
        for user, token in enumerate(tokens):
            for number in range(args.tabs):
                # Tabs open over the ramp, not all in the same millisecond.
                await asyncio.sleep(args.ramp / max(1, args.users * args.tabs))
                tasks.append(asyncio.create_task(stream(client, token, results, stop)))
                tasks.append(
                    asyncio.create_task(tab(client, token, user + number, results, stop, args))
                )
        await asyncio.gather(*tasks)
    return results


def report(results: Results, args: argparse.Namespace) -> dict:
    groups = sorted(set(results.latencies) | set(results.errors) | set(results.refusals))
    rows = []
    for group in groups:
        values = results.latencies.get(group, [])
        rows.append(
            {
                "group": group,
                "ok": len(values),
                "p50_ms": _ms(percentile(values, 0.50)),
                "p95_ms": _ms(percentile(values, 0.95)),
                "p99_ms": _ms(percentile(values, 0.99)),
                "max_ms": _ms(max(values) if values else None),
                "errors": results.errors.get(group, 0),
                "refusals": results.refusals.get(group, 0),
            }
        )
    main = [v for group in MAIN_READS for v in results.latencies.get(group, [])]
    summary = {
        "label": args.label,
        "base_url": args.base_url,
        "users": args.users,
        "tabs": args.tabs,
        "duration_seconds": args.duration,
        "groups": rows,
        "main_reads": {
            "ok": len(main),
            "p50_ms": _ms(percentile(main, 0.50)),
            "p95_ms": _ms(percentile(main, 0.95)),
            "p99_ms": _ms(percentile(main, 0.99)),
            "errors": sum(results.errors.get(group, 0) for group in MAIN_READS),
        },
        "requests_per_second": round(
            sum(len(v) for v in results.latencies.values()) / max(1, args.duration), 1
        ),
        "statuses": dict(sorted(results.statuses.items())),
        "streams": {
            "opened": results.stream_opened,
            "first_event_p50_ms": _ms(percentile(results.stream_first_event, 0.50)),
            "first_event_p95_ms": _ms(percentile(results.stream_first_event, 0.95)),
            "events": results.stream_events,
            "broken": results.stream_broken,
            "refused": results.stream_refused,
        },
        "sign_in": {
            "count": len(results.sign_in_seconds),
            "p50_ms": _ms(percentile(results.sign_in_seconds, 0.50)),
            "retries_on_rate_limit": results.sign_in_retries,
        },
    }
    print(f"\n{args.label or 'load test'}: {args.users} users x {args.tabs} tabs, "
          f"{args.duration}s against {args.base_url}")
    print(f"{'group':<14}{'ok':>7}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'max ms':>9}"
          f"{'errors':>8}{'4xx':>6}")
    for row in rows:
        print(f"{row['group']:<14}{row['ok']:>7}{_cell(row['p50_ms'])}{_cell(row['p95_ms'])}"
              f"{_cell(row['p99_ms'])}{_cell(row['max_ms'])}{row['errors']:>8}"
              f"{row['refusals']:>6}")
    m = summary["main_reads"]
    print(f"{'MAIN READS':<14}{m['ok']:>7}{_cell(m['p50_ms'])}{_cell(m['p95_ms'])}"
          f"{_cell(m['p99_ms'])}{'':>9}{m['errors']:>8}")
    s = summary["streams"]
    print(f"streams: {s['opened']} opened, first event p50 {s['first_event_p50_ms']} ms / "
          f"p95 {s['first_event_p95_ms']} ms, {s['events']} events, {s['broken']} broken, "
          f"{s['refused']} refused")
    print(f"throughput: {summary['requests_per_second']} successful reads/s; "
          f"statuses {summary['statuses']}")
    return summary


def _ms(value: float | None) -> float | None:
    return None if value is None else round(value * 1000, 1)


def _cell(value: float | None) -> str:
    return f"{'-' if value is None else value:>9}"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--origin", default=None, help="Origin header for sign-in (base URL)")
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--tabs", type=int, default=3)
    parser.add_argument("--duration", type=float, default=120.0, help="seconds of load")
    parser.add_argument("--ramp", type=float, default=20.0, help="seconds to open every tab")
    parser.add_argument("--think-min", type=float, default=3.0)
    parser.add_argument("--think-max", type=float, default=10.0)
    parser.add_argument("--per-tab-concurrency", type=int, default=5)
    parser.add_argument("--request-timeout", type=float, default=30.0)
    parser.add_argument("--username-pattern", default="load_u{n:02d}")
    parser.add_argument("--password-env", default="LOAD_TEST_PASSWORD")
    parser.add_argument("--sign-in-budget", type=float, default=300.0,
                        help="seconds the sign-ins may take, rate-limit waits included")
    parser.add_argument("--label", default="")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    args.origin = args.origin or args.base_url.rstrip("/")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    password = os.environ.get(args.password_env, "")
    if not password:
        print(f"set {args.password_env} to the load-test accounts' password", file=sys.stderr)
        return 2
    random.seed(args.seed)
    results = asyncio.run(run(args, password))
    summary = report(results, args)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

