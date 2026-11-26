"""A person browsing never hits a per-person limit: cold page loads replayed against the quotas.

The security review added per-person quotas on writes and heavy computations (trial and release
defaults 300 and 30 a minute) and one cap on open live streams. A demo crawl then found browsing
alone tripping the stream cap; the same cause could trip these: a page that sends a heavy
computation (or several writes) on load, multiplied by a person moving quickly through pages.
Measured (``tests/fixtures/client/cold_load_requests.json``): before the fix every cold load of
any page, for a role that may run it, sent ``POST /api/route-cost/resource-pool/optimize`` (the
pool optimiser's automatic run, 15 of 22 pages), so 30 page loads in a minute spent the whole
heavy quota. It now runs only on the pages that show its result (Position, Deals, Review).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from eurogas_nexus.core import shared_cache as cache_module
from eurogas_nexus.security import rate_limit

MIX = json.loads(
    (Path(__file__).resolve().parents[1] / "fixtures" / "client" / "cold_load_requests.json")
    .read_text(encoding="utf-8")
)["pages"]
#: The pages the pool optimiser's result is shown on (clients/web useAppController).
POOL_PAGES = ("contracts:", "scenario:")
#: A fast crawl: every page of the product, cold-loaded, twice within one minute (44 loads,
#: one every 1.4 s), well past what a person does by hand.
CRAWL_ROUNDS = 2


class _Shared(cache_module.MemoryCache):
    shared = True  # the quotas count through the shared cache, as with several processes


@pytest.fixture(autouse=True)
def _trial(monkeypatch):
    monkeypatch.setattr(rate_limit, "_production", lambda: True)  # the trial/release defaults
    monkeypatch.delenv(rate_limit.HEAVY_LIMIT_ENV, raising=False)
    monkeypatch.delenv(rate_limit.WRITE_LIMIT_ENV, raising=False)
    rate_limit._WINDOWS.clear()
    cache_module.use_cache(_Shared())
    yield
    cache_module.use_cache(None)
    rate_limit._WINDOWS.clear()


def _request(method: str, path: str, principal: str = "p-tester"):
    return SimpleNamespace(
        method=method,
        url=SimpleNamespace(path=path),
        state=SimpleNamespace(identity=SimpleNamespace(principal_id=principal)),
        client=SimpleNamespace(host="10.0.0.2"),  # every user behind one gateway address
    )


def _replay(pages, principal: str = "p-tester") -> list[str]:
    refused = []

    async def run():
        for page in pages:
            for line in MIX[page]:
                method, path = line.split(" ", 1)
                try:
                    await rate_limit.require_principal_quota(_request(method, path, principal))
                except HTTPException as exc:
                    assert exc.status_code == 429
                    refused.append(f"{page}: {line}")

    asyncio.run(run())
    return refused


def test_the_fixture_covers_the_pages_the_crawl_found():
    for page in ("market:overview", "market:curves", "contracts:overview", "market:network"):
        assert MIX[page], f"{page}: Today, Prices, Position and the map are recorded"


def test_a_fast_crawl_of_every_page_stays_within_the_quotas():
    assert _replay(list(MIX) * CRAWL_ROUNDS) == []


def test_two_people_sharing_one_gateway_address_do_not_share_a_quota():
    assert _replay(list(MIX) * CRAWL_ROUNDS, "p-one") == []
    assert _replay(list(MIX) * CRAWL_ROUNDS, "p-two") == []


def test_no_page_but_those_showing_the_pool_result_runs_a_heavy_computation_on_load():
    heavy_on_load = {
        page
        for page, lines in MIX.items()
        for line in lines
        if line.split(" ", 1)[0] != "GET"
        and line.split(" ", 1)[1].startswith(rate_limit.HEAVY_PREFIXES)
        and not page.startswith(POOL_PAGES)
    }
    # The LNG cargo study prices its own cargo once on open (one computation per load).
    assert heavy_on_load <= {"research:cargo"}
    worst = max(
        sum(
            1
            for line in lines
            if line.split(" ", 1)[0] != "GET"
            and line.split(" ", 1)[1].startswith(rate_limit.HEAVY_PREFIXES)
        )
        for lines in MIX.values()
    )
    assert worst <= 1, "one heavy computation per cold load at most"


def test_the_admin_throttle_counts_per_person_once_signed_in():
    async def run(principal: str, times: int) -> int:
        refused = 0
        for _ in range(times):
            try:
                await rate_limit.require_admin_rate_limit(_request("GET", "/api/setup", principal))
            except HTTPException:
                refused += 1
        return refused

    assert asyncio.run(run("p-admin-one", 120)) == 0
    # Another administrator behind the same gateway address has an allowance of their own.
    assert asyncio.run(run("p-admin-two", 120)) == 0
    assert asyncio.run(run("p-admin-one", 1)) == 1, "the limit itself still holds"
