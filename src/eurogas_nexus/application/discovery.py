"""Role-aware discovery (CP-24): findings the caller may read, ranked and phrased for a role.

Sources (each computed by the product's own calculation, never by a model):

- **opportunities** in the store, already filtered by book scope, source entitlement and the
  caller's own dismissals (``application/opportunities/listing``); new, blocked and ended
  records are left out;
- **credit** per counterparty with an approved line (``limits_service.credit_inputs``, the
  same legs and marks as the credit report): a breach today, or a projected breach under a
  stated price move with its tenor and the move that reaches the limit
  (``domain/discovery/credit_moves``);
- **mandates** in breach (``limits_service.mandate_usage_rows``).

A job function changes only the rank and the first sentence (``domain/discovery/findings``);
the reads run under the caller, so a finding the caller may not read is never built. The
sentence is the deterministic template; a model may rephrase it later from the same facts
(``phrasing`` says which was used).
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.discovery.credit_moves import credit_under_moves
from eurogas_nexus.domain.discovery.findings import (
    Finding,
    audience_of,
    phrase,
    rank,
    weight,
)
from eurogas_nexus.domain.opportunities.claims import grouped
from eurogas_nexus.domain.opportunities.model import Lane
from eurogas_nexus.domain.valuation.quality import CLASS_LABEL, InputClass

MAX_ITEMS = 25
CACHE_SECONDS = 60
_CACHE: dict[tuple, tuple[float, dict]] = {}

CREDIT_METHOD = (
    "Mark-to-market sensitivity, not a potential-future-exposure model: every remaining "
    "month facing the counterparty revalued with the forward mark moved by the stated "
    "percentage; the reach move is found by bisection; the tenor is the first month whose "
    "cumulative exposure crosses the limit."
)


def _aware(moment: datetime) -> datetime:
    """A stored time as UTC (SQLite returns it naive)."""

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _money(value: float | Decimal, currency: str) -> str:
    return f"{currency} {grouped(Decimal(str(value)))}"


def opportunity_findings(session, principal, now: datetime) -> list[Finding]:
    """Shown opportunities the caller may read, as findings."""

    from eurogas_nexus.application.opportunities.listing import user_states, visible_records

    rows = visible_records(session, principal)
    mine = user_states(session, getattr(principal, "principal_id", None), [r.opp_key for r in rows])
    out = []
    for row in rows:
        if row.state not in {"actionable", "indicative", "watch"}:
            continue
        held = mine.get(row.opp_key)
        if held is not None and held.state == "dismissed" and held.at_version == row.version:
            continue
        must = row.lane == Lane.MUST_ACT.value
        severity = 3 if must else (2 if row.state != "watch" else 1)
        value = row.value_amount
        size = Decimal(str(row.reporting_value or value or row.volume_value or 0))
        places = 3 if "/MWh" in row.headline_unit else 0
        headline = f"{grouped(Decimal(str(row.headline_value)), places)} {row.headline_unit}"
        out.append(
            Finding(
                finding_id=f"opportunity:{row.opportunity_id}",
                kind=(f"market.{row.type}" if row.lane == "market" else f"opportunity.{row.type}"),
                severity=severity,
                facts={
                    "subject": str(
                        (row.claim_fields or {}).get("contract")
                        or "|".join(
                            str((row.claim_fields or {}).get(key) or "")
                            for key in ("buy_hub", "sell_hub", "hub", "asset")
                        )
                    ),
                    "claim": row.claim_text,
                    "period": row.period_start.isoformat()
                    if row.type == "event_exposure"
                    else row.period_label,
                    "headline": headline,
                    "value": "-" if value is None else _money(value, row.value_currency),
                },
                input_class=InputClass(row.quality_class),
                simulated=row.simulated,
                value=None if value is None else Decimal(str(value)),
                value_unit=row.value_currency or "",
                size=size,
                evidence=(
                    {
                        "opportunity_id": row.opportunity_id,
                        "state": row.state,
                        "snapshot_id": row.snapshot_id,
                        "reasons": list(row.reasons or []),
                        "as_of_utc": _aware(row.last_evaluated_utc).isoformat(),
                    },
                ),
                book_ids=tuple(row.book_ids or ()),
                link={"page": "deals/opportunities", "opportunity_id": row.opportunity_id},
                due_utc=row.deadline_utc,
            )
        )
    return out


def credit_findings(caller, today) -> list[Finding]:
    """A breach today, or the smallest stated move that breaches, per counterparty."""

    from eurogas_nexus.application.limits_service import credit_inputs

    built = credit_inputs(caller, today)
    klass = InputClass.SIMULATED if built.simulated_marks else InputClass.INDICATIVE
    out = []
    for item in built.lines:
        moves = credit_under_moves(item.line, item.legs, today=today, mark=built.mark, fx=built.fx)
        currency = moves.currency
        evidence = [
            {
                "move_pct": round(100 * result.move),
                "net_exposure": round(result.net_exposure, 2),
                "breach": result.breach,
                "tenor": result.tenor,
            }
            for result in moves.moves
        ]
        common = {
            "counterparty": moves.name,
            "exposure": _money(moves.net_exposure, currency),
            "limit": _money(moves.limit, currency),
        }
        link = {"page": "book/limits", "counterparty_id": moves.counterparty_id}
        if moves.status == "breach":
            out.append(
                Finding(
                    finding_id=f"credit:{moves.counterparty_id}",
                    kind="credit.breach",
                    severity=3,
                    facts=common,
                    input_class=klass,
                    simulated=klass is InputClass.SIMULATED,
                    value=Decimal(str(round(moves.net_exposure - moves.limit, 2))),
                    value_unit=currency,
                    size=Decimal(str(round(moves.net_exposure, 2))),
                    evidence=tuple(evidence),
                    book_ids=item.books,
                    link=link,
                    method=CREDIT_METHOD,
                )
            )
            continue
        projected = moves.projected
        if projected is None or moves.reach_move is None:
            continue
        move_price = moves.reach_price_move
        out.append(
            Finding(
                finding_id=f"credit-projected:{moves.counterparty_id}",
                kind="credit.projected",
                severity=2,
                facts={
                    **common,
                    "hub": moves.front_hub or "the curve",
                    "move_pct": f"{100 * moves.reach_move:+.1f} %",
                    "move_price": "-"
                    if move_price is None
                    else f"{move_price:+.2f} {currency}/MWh on {moves.front_mark:.2f}",
                    "shock": f"{100 * projected.move:+.0f} %",
                    "tenor": projected.tenor or "-",
                },
                input_class=klass,
                simulated=klass is InputClass.SIMULATED,
                value=None if move_price is None else Decimal(str(round(move_price, 4))),
                value_unit=f"{currency}/MWh",
                size=Decimal(str(round(moves.net_exposure, 2))),
                evidence=tuple(evidence),
                book_ids=item.books,
                link=link,
                method=CREDIT_METHOD,
            )
        )
    return out


def mandate_findings(caller, today) -> list[Finding]:
    """Mandates in breach."""

    from eurogas_nexus.application.limits_service import mandate_usage_rows
    from eurogas_nexus.core.config import demo_marks_allowed

    rows = mandate_usage_rows(caller, today)
    klass = InputClass.SIMULATED if demo_marks_allowed() else InputClass.INDICATIVE
    out = []
    for row, books in zip(rows.rows, rows.books, strict=False):
        if row.get("status") != "breach":
            continue
        out.append(
            Finding(
                finding_id=f"mandate:{row['mandate_id']}",
                kind="mandate.breach",
                severity=3,
                facts={
                    "mandate": str(row.get("name") or row["mandate_id"]),
                    "detail": str(row.get("breaches") or "limit exceeded"),
                },
                input_class=klass,
                simulated=klass is InputClass.SIMULATED,
                size=Decimal(str(row.get("utilisation_pct") or 0)),
                evidence=(
                    {
                        k: row.get(k)
                        for k in ("utilisation_pct", "largest_net_mwh", "largest_at", "breaches")
                    },
                ),
                book_ids=tuple(books or ()),
                link={"page": "book/limits", "mandate_id": str(row["mandate_id"])},
            )
        )
    return out


def _subject(item: Finding) -> tuple:
    """What makes two findings the same story: one contract, or one hub pair, per kind."""

    facts = item.facts
    return (item.kind, facts.get("subject") or item.finding_id)


def _grouped(findings: list[Finding]) -> list[Finding]:
    """One item per subject (the most urgent one), counting the others in ``facts['more']``."""

    from dataclasses import replace

    groups: dict[tuple, list[Finding]] = {}
    for item in findings:
        groups.setdefault(_subject(item), []).append(item)
    far = datetime.max.replace(tzinfo=UTC)
    out = []
    for members in groups.values():
        lead = min(
            members,
            key=lambda item: (-item.severity, item.due_utc or far, -abs(item.size)),
        )
        if len(members) > 1:
            lead = replace(lead, facts={**lead.facts, "more": str(len(members) - 1)})
        out.append(lead)
    return out


def discoveries(
    session,
    request_or_caller,
    *,
    function: str | None,
    language: str = "en",
    limit: int = MAX_ITEMS,
    now: datetime | None = None,
) -> dict[str, Any]:
    """The caller's findings ranked for ``function`` (one of their job functions)."""

    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.opportunities.listing import latest_evaluation

    caller = caller_of(request_or_caller)
    principal = caller.principal
    moment = now or datetime.now(UTC)
    audience = audience_of(function)
    evaluation = latest_evaluation(session)
    bind = session.get_bind() if hasattr(session, "get_bind") else None
    key = (
        # The store as well as the caller: one process can hold several stores (tests, tools).
        str(getattr(bind, "url", "")),
        getattr(principal, "principal_id", None),
        audience,
        language,
        limit,
        None if evaluation is None else evaluation.evaluation_id,
        moment.date(),
    )
    cached = _CACHE.get(key)
    if cached is not None and time.monotonic() - cached[0] < CACHE_SECONDS:
        return cached[1]
    findings: list[Finding] = []
    warnings: list[str] = []
    findings += opportunity_findings(session, principal, moment)
    from eurogas_nexus.security.authorization import Permission, authorize

    if authorize(principal, Permission.PORTFOLIO_READ).allowed:
        for source in (credit_findings, mandate_findings):
            try:
                findings += source(caller, moment.date())
            except Exception as exc:  # noqa: BLE001 - one source failing hides only itself
                warnings.append(
                    f"{source.__name__.split('_')[0]} findings unavailable: {type(exc).__name__}"
                )
    ranked = rank(_grouped(findings), audience)[: max(1, min(limit, MAX_ITEMS))]
    items = [
        {
            "finding_id": item.finding_id,
            "kind": item.kind,
            "severity": item.severity,
            "relevance": weight(item.kind, audience),
            "sentence": phrase(item, audience, language)
            + (
                ""
                if not item.facts.get("more")
                else (
                    f"（另有 {item.facts['more']} 项同类）"
                    if language.lower().startswith("zh")
                    else f" (+{item.facts['more']} more like this)"
                )
            ),
            "phrasing": "template",
            "value": None
            if item.value is None
            else {"value": str(item.value), "unit": item.value_unit},
            "quality": {"class": item.input_class.value, "label": CLASS_LABEL[item.input_class]},
            "simulated": item.simulated,
            "book_ids": list(item.book_ids),
            "link": dict(item.link),
            "due_utc": item.due_utc.isoformat() if item.due_utc else None,
            "evidence": list(item.evidence),
            "method": item.method or None,
        }
        for item in ranked
    ]
    payload = {
        "audience": audience,
        "function": function,
        "language": "zh" if language.lower().startswith("zh") else "en",
        "as_of_utc": moment.isoformat(),
        "items": items,
        "total": len(findings),
        "warnings": warnings,
    }
    _CACHE[key] = (time.monotonic(), payload)
    if len(_CACHE) > 512:
        _CACHE.clear()
    return payload
