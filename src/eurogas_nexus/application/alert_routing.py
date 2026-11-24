"""Who an alert is for: its owner, its escalation and the notification category it travels in.

Each monitoring alert category has one owner, the job
function whose work it changes, and one escalation, the function told when the owner does not
act. The owner and escalation are job functions (``security.capabilities.FunctionalAssignment``),
never roles: they say who should look, and grant nothing.

The notification category decides which channels receive the message (Settings ->
Notifications). ``opportunity`` (the trading desk), ``nomination`` (scheduling and deliveries)
and ``source`` (data operations) are routed on their own since M7; a channel that subscribed to
``alert`` before keeps receiving all three (:data:`UMBRELLA`), so no channel loses a message it
had. Dedupe, materiality and cooldown are unchanged: the outbox writes each alert once
(``notifications.queue_notification``), the opportunity engine cuts a new version only on a
material change, and a failed delivery is retried at most three times, five minutes apart.

The full table, with the routes still missing, is in
``docs/engineering/Commercial-Intelligence-V3/15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Route:
    """Where one kind of alert goes."""

    notification_category: str
    owner: str
    escalation: str


#: Monitoring alert category -> route.
ROUTES: dict[str, Route] = {
    "opportunity": Route("opportunity", "TRADER", "MANAGEMENT"),
    "market_opportunity": Route("opportunity", "TRADER", "MANAGEMENT"),
    "limits": Route("limits", "RISK_MANAGER", "MANAGEMENT"),
    "delivery": Route("nomination", "OPERATIONS", "TRADER"),
    "physical": Route("alert", "TRADER", "RISK_MANAGER"),
    "market": Route("alert", "TRADER", "MANAGEMENT"),
    "fundamentals": Route("alert", "HQ_BUSINESS_ANALYST", "TRADER"),
    "strategy": Route("alert", "QUANT_RESEARCHER", "TRADER"),
    "data_source": Route("source", "DATA_OPERATOR", "PLATFORM_ADMINISTRATOR"),
}

#: Gas-day steps due or overdue (``gas_day_checklist.queue_deadline_notifications``).
NOMINATION_DEADLINE = Route("nomination", "OPERATIONS", "TRADER")

#: Anything without a route of its own.
DEFAULT_ROUTE = Route("alert", "TRADER", "MANAGEMENT")

#: Categories an ``alert`` subscription also receives (they were ``alert`` before M7).
UMBRELLA: dict[str, frozenset[str]] = {
    "alert": frozenset({"opportunity", "nomination", "source"}),
}


def route_for(category: str | None) -> Route:
    """The route of a monitoring alert category."""

    return ROUTES.get(category or "", DEFAULT_ROUTE)


def addressed_line(route: Route) -> str:
    """The line a notification body ends with, so a shared mailbox knows whose it is."""

    owner = route.owner.replace("_", " ").title()
    escalation = route.escalation.replace("_", " ").title()
    return f"For: {owner}. If not acted on: {escalation}."
