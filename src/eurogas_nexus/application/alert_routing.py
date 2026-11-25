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

A change to one of the firm's cargoes (LNG-2, ``application/lng_cargo_alerts``) raises up to
four alerts, one per role, each in the category its readers already subscribe to: the hedge
proposal to the LNG desk (``cargo``), the berth, send-out and nominations to scheduling
(``nomination``), the exposure and mandates to risk (``limits``), and a material change to the
desk head (``desk_head``). Those alerts are notified by their consumer, with its own dedupe,
cooldown and withdrawal (:data:`SELF_NOTIFYING`), not by the alert mirror. So are the gas day's
reconciliation breaks near a cut-off (SCHED-1, ``application/gas_day_reconciliation``,
category ``gas_day_break``), which go to scheduling in ``nomination``.

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
    # TAR-1: a capacity auction or LNG slot window opening within three days goes to
    # scheduling, as nominations do; the desk is told when scheduling does not act.
    "capacity": Route("nomination", "OPERATIONS", "TRADER"),
    # LNG-2: one cargo change, one alert per role.
    "lng_hedge": Route("cargo", "TRADER", "MANAGEMENT"),
    "lng_schedule": Route("nomination", "OPERATIONS", "TRADER"),
    "lng_exposure": Route("limits", "RISK_MANAGER", "MANAGEMENT"),
    "lng_material": Route("desk_head", "MANAGEMENT", "MANAGEMENT"),
    # SCHED-1: a reconciliation break near a cut-off, to scheduling.
    "gas_day_break": Route("nomination", "OPERATIONS", "TRADER"),
}

#: The cargo roles (``domain.lng.consequences.ROLES``) and the alert category of each.
CARGO_ROLE_CATEGORIES: dict[str, str] = {
    "trader": "lng_hedge",
    "scheduler": "lng_schedule",
    "risk": "lng_exposure",
    "desk_head": "lng_material",
}

#: Alert categories whose consumer queues their notifications (dedupe, cooldown, withdrawal):
#: the alert mirror leaves them alone and the monitoring scan does not resolve them.
SELF_NOTIFYING = frozenset({*CARGO_ROLE_CATEGORIES.values(), "gas_day_break"})

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
    if route.owner == route.escalation:
        return f"For: {owner}."
    return f"For: {owner}. If not acted on: {escalation}."
