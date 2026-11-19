"""One hook: "the inputs of these instruments changed", raised where ticks are stored.

The tick ingestion (``application/market_ticks.ingest_ticks``) stores a batch and then calls
:func:`notify_inputs_changed` with the instruments the batch touched, in the same session and
transaction, before it commits. Anything that evaluates on arrival subscribes once, at import
time, with :func:`subscribe_inputs_changed`: the tracked strategies do
(``application/strategy_tracking``), and the prompt-type opportunity evaluators may.

Instrument keys are ``"HUB|product"`` with the stored quote product key (``"TTF|within-day"``,
``"TTF|day-ahead"``, ``"NBP|month-ahead"``). ``at`` is the evaluation instant (the wall clock,
or a simulated session's exchange time in a replay). A handler must not commit, must be quick
(it runs inside the ingestion request) and should debounce itself; one handler raising does
not stop the others (its error is returned in its result).

No queue, broker or second service (AGENTS.md rule 5): PostgreSQL stays the event log.

行情输入变化钩子：逐笔入库后、提交前，按合约通知订阅者（跟踪策略、日内机会评估器）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

#: handler(session, instruments, at, replay) -> a small JSON-able result
InputsChangedHandler = Callable[[Session, frozenset[str], datetime, bool], dict[str, Any]]

_HANDLERS: dict[str, InputsChangedHandler] = {}


def subscribe_inputs_changed(name: str, handler: InputsChangedHandler) -> None:
    """Register ``handler`` under ``name`` (registering a name again replaces it)."""

    _HANDLERS[name] = handler


def subscribers() -> tuple[str, ...]:
    return tuple(_HANDLERS)


def notify_inputs_changed(
    session: Session, instruments: frozenset[str], *, at: datetime, replay: bool = False
) -> dict[str, dict[str, Any]]:
    """Call every subscriber for the instruments that changed; returns each one's result."""

    _load_builtin_subscribers()
    results: dict[str, dict[str, Any]] = {}
    if not instruments:
        return results
    for name, handler in list(_HANDLERS.items()):
        try:
            with session.begin_nested():
                results[name] = handler(session, instruments, at, replay)
        except Exception as exc:  # noqa: BLE001 - one subscriber failing hides only itself
            results[name] = {"error": type(exc).__name__}
    return results


def _load_builtin_subscribers() -> None:
    # Importing a subscriber's module registers it.
    import eurogas_nexus.application.strategy_tracking  # noqa: F401
