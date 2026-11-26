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
