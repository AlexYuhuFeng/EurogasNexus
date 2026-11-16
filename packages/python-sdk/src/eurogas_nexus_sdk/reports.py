"""SDK client for market reports (``/api/reports/...``).

A report is assembled by the server from the catalogue's sections, as the calling principal
(its licences and books), stored once and reopened by id. The HTML is one self-contained
file; PDF is produced by printing it. Nothing here trades, nominates or settles.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta, SdkProtocolError, api_url, get_envelope


class ReportMetadata(BaseModel):
    """A stored report's metadata (``GET /api/reports/market/{report_id}``)."""

    model_config = ConfigDict(extra="allow")

    report_id: str
    title: str
    kind: str
    audience: str
    headline: str
    key_points: list[str] = Field(default_factory=list)
    as_of: str
    simulated: bool
    sections: list[dict[str, Any]] = Field(default_factory=list)
    omitted: list[dict[str, Any]] = Field(default_factory=list)
    licensed: dict[str, Any] = Field(default_factory=dict)
    model_use: dict[str, Any] = Field(default_factory=dict)
    snapshot_sha256: str
    html_sha256: str


def _post(url: str, body: dict[str, Any], timeout: float) -> tuple[Any, ResponseMeta]:
    response = _http.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or "data" not in payload or "meta" not in payload:
        raise SdkProtocolError("Backend response is missing data/meta envelope fields.")
    return payload["data"], ResponseMeta.model_validate(payload["meta"])


def fetch_report_catalogue(base_url: str) -> dict[str, Any]:
    """Report kinds, sections (data source, chart types, audience) and default plans."""

    data, _ = get_envelope(api_url(base_url, "reports/catalogue"))
    return data


def propose_report_plan(base_url: str, question: str, *, audience: str = "internal",
                        use_model: bool = True) -> dict[str, Any]:
    """A validated, editable plan for a question (``POST /api/reports/plan``)."""

    data, _ = _post(api_url(base_url, "reports/plan"),
                    {"question": question, "audience": audience, "use_model": use_model}, 60.0)
    return data


def generate_market_report(base_url: str, **plan: Any) -> ReportMetadata:
    """Generate and store a report (``POST /api/reports/market``); returns its metadata.

    ``plan`` takes the request fields: ``kind``, ``variant``, ``audience``, ``sections``,
    ``hubs``, ``countries``, ``period_start``, ``period_end``, ``alert_id``, ``outage_id``,
    ``question``, ``language``, ``use_model``.
    """

    data, _ = _post(api_url(base_url, "reports/market"), plan, 180.0)
    return ReportMetadata.model_validate(data)


def list_market_reports(base_url: str, *, kind: str | None = None,
                        limit: int = 50) -> list[dict[str, Any]]:
    """Stored reports the caller may open, newest first."""

    params: dict[str, Any] = {"limit": limit}
    if kind:
        params["kind"] = kind
    data, _ = get_envelope(api_url(base_url, "reports/market"), params=params)
    return list(data)


def fetch_market_report(base_url: str, report_id: str) -> ReportMetadata:
    data, _ = get_envelope(api_url(base_url, f"reports/market/{report_id}"))
    return ReportMetadata.model_validate(data)


def fetch_market_report_html(base_url: str, report_id: str) -> str:
    """The stored report as one self-contained HTML file."""

    response = _http.get(api_url(base_url, f"reports/market/{report_id}/html"), timeout=30.0)
    response.raise_for_status()
    return response.text


__all__ = [
    "ReportMetadata",
    "fetch_market_report",
    "fetch_market_report_html",
    "fetch_report_catalogue",
    "generate_market_report",
    "list_market_reports",
    "propose_report_plan",
]
