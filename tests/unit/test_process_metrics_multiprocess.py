"""With N API workers, whichever worker answers the scrape reports every worker's samples."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

_WORKER = textwrap.dedent(
    """
    from eurogas_nexus.application import process_metrics
    process_metrics.observe_request("/api/market/curves/{hub}", "GET", 200, 0.2)
    process_metrics.observe_request("/api/market/curves/{hub}", "GET", 500, 2.0)
    process_metrics.stream_opened("quotes")
    """
)

# One API worker: its pool counted (db.session.pool_counters) and its poller polled.
_SERVING_WORKER = textwrap.dedent(
    """
    from eurogas_nexus.application import process_metrics
    from eurogas_nexus.db import session
    counters = session.pool_counters()
    for _ in range(3):
        counters.record(0.0, timed_out=False, exhausted=False)
    counters.record(0.25, timed_out=False, exhausted=True)
    counters.record(1.0, timed_out=True, exhausted=True)
    process_metrics.observe_pools([], force=True)
    process_metrics.stream_poll(0.5, failed=False)
    process_metrics.stream_poll(0.5, failed=True)
    process_metrics.stream_refused()
    """
)

_SCRAPER = textwrap.dedent(
    """
    from eurogas_nexus.application import process_metrics
    print(process_metrics.render())
    """
)


def _run(code: str, directory: str) -> str:
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": directory}
    result = subprocess.run(  # noqa: S603 - this interpreter, fixed code
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    )
    return result.stdout


_COUNT = 'eurogas_http_request_duration_seconds_count{method="GET",route_group="/api/market"}'
_ERRORS = (
    'eurogas_http_requests_total{method="GET",route_group="/api/market",status_class="5xx"}'
)


def _value(text: str, prefix: str) -> float:
    for line in text.splitlines():
        if line.startswith(prefix):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{prefix} not in:\n{text}")


def test_two_workers_are_summed_by_a_third(tmp_path) -> None:
    directory = str(tmp_path / "metrics")
    _run(_WORKER, directory)
    _run(_WORKER, directory)
    text = _run(_SCRAPER, directory)
    assert _value(text, _ERRORS) == 2.0
    assert _value(text, _COUNT) == 4.0


def test_a_dead_workers_live_gauges_are_dropped_at_start(tmp_path) -> None:
    """Counters of a dead worker stay (a total never drops); its open streams do not."""

    directory = str(tmp_path / "metrics")
    _run(_WORKER, directory)
    text = _run(
        "from eurogas_nexus.application import process_metrics\n"
        "process_metrics.prepare_process()\n"
        "print(process_metrics.render())\n",
        directory,
    )
    assert 'eurogas_stream_connections{topic="quotes"} 1.0' not in text
    assert _value(text, _COUNT) == 2.0


def test_pool_and_poller_counters_of_two_workers_are_summed_once(tmp_path) -> None:
    directory = str(tmp_path / "metrics")
    _run(_SERVING_WORKER, directory)
    _run(_SERVING_WORKER, directory)
    text = _run(_SCRAPER, directory)
    expected = {
        "eurogas_db_pool_checkouts_total": 8.0,
        "eurogas_db_pool_waits_total": 4.0,
        "eurogas_db_pool_timeouts_total": 2.0,
        "eurogas_db_pool_wait_seconds_total": 2.5,
        "eurogas_stream_polls_total": 4.0,
        "eurogas_stream_poll_seconds_total": 2.0,
        "eurogas_stream_poll_failures_total": 2.0,
        "eurogas_stream_refused_total": 2.0,
    }
    for name, value in expected.items():
        assert _value(text, name + " ") == value, name
        # One family per metric (the multi-process exposition names it with ``_total``).
        assert text.count(f"# TYPE {name} counter") == 1, name
