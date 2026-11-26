"""``@states_manual_inputs``: one line that makes a calculation route state its hand-entered
inputs (``meta.manual_inputs``, AGENTS.md rule 19; builder in ``application/manual_inputs``).

    @router.post("/api/portfolio/sell-down-plan")
    @states_manual_inputs(include=("da_price", "wd_expected_price"), units={...})
    def post_sell_down_plan(body: SellDownBody, request: Request) -> dict: ...

The decorator reads the request body the route was given (the first pydantic argument) and
the request, and writes the list onto the envelope the route returns, whatever path it
returned by. A route whose result reads hand entries from the store adds them itself with
``application.manual_inputs.manual_input``; the decorator keeps those.
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from eurogas_nexus.application.manual_inputs import from_request_body

#: Routes wired with the decorator (path is filled by the census test from the router).
WIRED: list[str] = []


def states_manual_inputs(
    *,
    include: Iterable[str] | None = None,
    exclude: Iterable[str] = (),
    units: Mapping[str, str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    keep = tuple(include) if include is not None else None

    def decorate(handler: Callable[..., Any]) -> Callable[..., Any]:
        WIRED.append(f"{handler.__module__}.{handler.__name__}")

        def attach(result: Any, kwargs: dict[str, Any]) -> Any:
            if not isinstance(result, dict) or not isinstance(result.get("meta"), dict):
                return result
            body = next(
                (value for value in kwargs.values() if hasattr(value, "model_fields_set")), None
            )
            request = next(
                (value for value in kwargs.values() if hasattr(value, "state")
                 and hasattr(value, "url")),
                None,
            )
            found = (
                from_request_body(body, request, include=keep, exclude=exclude, units=units)
                if body is not None
                else []
            )
            held = result["meta"].get("manual_inputs") or []
            result["meta"]["manual_inputs"] = [*held, *found]
            return result

        if inspect.iscoroutinefunction(handler):

            @functools.wraps(handler)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                return attach(await handler(*args, **kwargs), kwargs)

            return async_wrapper

        @functools.wraps(handler)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return attach(handler(*args, **kwargs), kwargs)

        return wrapper

    return decorate
