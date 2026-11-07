"""HTTP adapters for the position inputs in :mod:`eurogas_nexus.application.position_inputs`.

The calculation lives in the application layer; these wrappers give the API routes the
caller from the request and a 503 when the runtime store is down.
"""

from __future__ import annotations

from fastapi import Request

from eurogas_nexus.api.routes.public.portfolio_common import db_unavailable
from eurogas_nexus.application import position_inputs as _inputs
from eurogas_nexus.application.position_inputs import (  # noqa: F401 - shared helpers
    HUB_CURRENCY,
    LadderInputs,
    books_by_id,
    contract_price_in_hub_currency,
    fx_by_hub_for,
    gas_year_window,
    hub_from_text,
    rollup,
)


def ladder_inputs(request: Request, today, horizon_start, horizon_end) -> LadderInputs:
    """The caller's legs and marks; 503 when the runtime store is unavailable."""

    from sqlalchemy.exc import SQLAlchemyError

    try:
        return _inputs.ladder_inputs(request, today, horizon_start, horizon_end)
    except SQLAlchemyError as exc:
        raise db_unavailable(exc) from exc
