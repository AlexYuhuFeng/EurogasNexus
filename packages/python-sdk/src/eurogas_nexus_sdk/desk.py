"""SDK client for the desk's Today read: ``GET /api/desk/today``.

One server computation of what changed and whether it touches the book: key figures
(prices and day change, positions, the tightest limit), what changed (alerts, outages),
the book against the market and the fundamentals. Every figure carries ``unit``,
``as_of``, ``state`` (current, late, stale, never, manual) and ``simulated``. Read only:
nothing is written and no model is called.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus_sdk._transport import SdkResult, api_url, get_envelope

RowKey = Literal["key_figures", "changes", "book", "fundamentals"]


class StaleFigure(BaseModel):
    """A late or stale figure named on its own (FRESH-02).

    Attributes:
        key: Stable figure key.
        label: Desk label of the figure.
        state: ``late`` or ``stale``.
        as_of: ISO-8601 time of the figure's data; None when never received.
    """

    model_config = ConfigDict(extra="allow")

    key: str
    label: str
    state: str
    as_of: str | None = None


class DeskToday(BaseModel):
    """The Today read for the calling principal.

    Attributes:
        as_of: ISO-8601 UTC time the read was computed.
        gas_day: Gas-day label the read is for.
        front_month: Front-month label (``Dec-26``).
        simulated: True when any figure uses simulated demo data.
        simulated_notice: The notice to show with simulated figures; None otherwise.
        rows: The four rows in display order (``key_figures``, ``changes``, ``book``,
            ``fundamentals``); each is a dict whose ``key`` names it. Their figures keep
            the server's units; nothing is converted here.
        stale_figures: Every late or stale figure by name.
        warnings: Non-blocking warnings.
    """

    model_config = ConfigDict(extra="allow")

    as_of: str
    gas_day: str
    front_month: str
    simulated: bool
    simulated_notice: str | None = None
    rows: list[dict[str, Any]] = Field(default_factory=list)
    stale_figures: list[StaleFigure] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def row(self, key: RowKey) -> dict[str, Any] | None:
        """The row named ``key``, or None when the server did not return it."""

        return next((row for row in self.rows if row.get("key") == key), None)


def fetch_desk_today(base_url: str) -> DeskToday:
    """Fetch the Today read, returning only the payload data.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        The Today read; response metadata is dropped.

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
    """
    return fetch_desk_today_result(base_url).data


def fetch_desk_today_result(base_url: str) -> SdkResult[DeskToday]:
    """Fetch the Today read together with backend response metadata.

    A server without a runtime database answers with an empty ``data`` object and the
    ``RUNTIME_DB_NOT_CONFIGURED`` warning; that is returned as a validation error here
    rather than as a Today read with invented defaults.

    Args:
        base_url: Operator-provided server root URL.

    Returns:
        An SdkResult whose data holds the Today read and whose meta carries the backend
        envelope (warnings, source references).

    Raises:
        httpx.HTTPStatusError: If the backend responds with a non-2xx status.
        pydantic.ValidationError: If the payload is not a Today read.
    """
    data, meta = get_envelope(api_url(base_url, "desk/today"), timeout_seconds=15.0)
    return SdkResult(DeskToday.model_validate(data), meta)
