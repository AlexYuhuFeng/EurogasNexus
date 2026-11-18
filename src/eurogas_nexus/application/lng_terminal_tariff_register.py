"""The public LNG terminal tariff register (CP-11): operators, documents, review, pricing.

**Terms first.** No operator document is read unless the firm has recorded that operator's
permission (``record_operator_permission``, ADMIN, audited). The terms check of 2026-11-18
(``OPERATOR_TERMS``, docs/legal/DATA_SOURCE_TERMS.md) found that Fluxys and Elengy forbid
reproduction or commercial reuse of their site content without written permission and that
DET publishes no reuse terms, so all three start as ``needs_firm_terms``. The product never
records a permission on the firm's behalf.

**Versioned, never overwritten.** Each document becomes candidate rows keyed by its SHA-256;
the same document again changes nothing; a new document adds rows and queues one attention
item ("Fluxys LNG tariff changed: review 3 values"). Rows move to ``REVIEWED`` only by a
second person (four eyes: the reviewer is never the one who recorded them). Only reviewed rows
price an actionable figure; candidate rows price "indicative".
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.route_cost.terminal_tariff_register import (
    CANDIDATE,
    REVIEWED,
    PublicTariff,
    TerminalCharge,
    resolve_terminal_charge,
)


@dataclass(frozen=True)
class OperatorTerms:
    """What an operator's published terms say about reuse (checked, quoted <= 25 words)."""

    operator: str
    display_name: str
    terminals: tuple[str, ...]  # terminal id prefixes
    legal_url: str
    finding: str
    checked_on: str


#: The terms check (2026-11-18): each operator's legal notice, as read.
OPERATOR_TERMS: dict[str, OperatorTerms] = {
    "fluxys_lng": OperatorTerms(
        operator="fluxys_lng",
        display_name="Fluxys LNG (Zeebrugge)",
        terminals=("zeebrugge",),
        legal_url="https://www.fluxys.com/en/legalnotice",
        finding=(
            "No reproduction, rental, lease, download ... of this site and its content ... "
            "without the prior written consent of Fluxys"
        ),
        checked_on="2026-11-18",
    ),
    "elengy": OperatorTerms(
        operator="elengy",
        display_name="Elengy (Montoir, Fos Cavaou, Fos Tonkin)",
        terminals=("montoir", "fos-cavaou", "fos-tonkin"),
        legal_url="https://www.elengy.com/en/legal-notice",
        finding=(
            "Any total or partial representation, modification or reproduction ... without "
            "the express permission of Elengy is strictly forbidden"
        ),
        checked_on="2026-11-18",
    ),
    "det": OperatorTerms(
        operator="det",
        display_name="Deutsche Energy Terminal (Brunsbüttel, Wilhelmshaven)",
        terminals=("brunsbuttel", "wilhelmshaven"),
        legal_url="https://energy-terminal.de/en/imprint",
        finding="The imprint publishes no terms of reuse; written confirmation is needed.",
        checked_on="2026-11-18",
    ),
}

NEEDS_FIRM_TERMS = "needs_firm_terms"
PERMITTED = "permitted"


class TariffRegisterError(ValueError):
    """A refused register action; ``code`` is stable for the API."""

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def operator_for_terminal(terminal_id: str) -> str | None:
    prefix = terminal_id.split(":")[0]
    for terms in OPERATOR_TERMS.values():
        if prefix in terms.terminals:
            return terms.operator
    return None


def _now(now_utc: datetime | None) -> datetime:
    return now_utc or datetime.now(UTC)


def _audit(
    session, *, actor: str, action: str, resource: str, outcome: str, detail: str, now: datetime
) -> None:
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="governance.data",
        principal=actor[:128],
        action=action,
        resource=resource,
        outcome=outcome,
        severity="info",
        detail=detail[:900],
        source_system="lng-terminal-tariffs",
        now_utc=now,
    )


# --- operator terms -------------------------------------------------------------------------


def operator_state(session, operator: str) -> dict[str, Any]:
    from eurogas_nexus.db.models import LngTerminalOperatorTermsRecord

    terms = OPERATOR_TERMS[operator]
    row = session.get(LngTerminalOperatorTermsRecord, operator)
    return {
        "operator": operator,
        "display_name": terms.display_name,
        "legal_url": terms.legal_url,
        "finding": terms.finding,
        "checked_on": terms.checked_on,
        "permission_state": row.permission_state if row else NEEDS_FIRM_TERMS,
        "reference": row.reference if row else None,
        "recorded_by": row.recorded_by if row else None,
        "recorded_at_utc": row.recorded_at_utc.isoformat() if row and row.recorded_at_utc else None,
    }


def operator_permitted(session, operator: str) -> bool:
    return operator_state(session, operator)["permission_state"] == PERMITTED


def record_operator_permission(
    session,
    operator: str,
    *,
    permitted: bool,
    reference: str,
    actor: str,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Record (or withdraw) the firm's permission to reuse an operator's documents."""

    from eurogas_nexus.db.models import LngTerminalOperatorTermsRecord

    if operator not in OPERATOR_TERMS:
        raise TariffRegisterError("operator_unknown", f"Unknown operator {operator!r}.", 404)
    if permitted and not reference.strip():
        raise TariffRegisterError(
            "reference_required",
            "Name the permission (letter, contract clause or e-mail) the firm holds.",
            422,
        )
    now = _now(now_utc)
    row = session.get(LngTerminalOperatorTermsRecord, operator)
    if row is None:
        row = LngTerminalOperatorTermsRecord(operator=operator, permission_state=NEEDS_FIRM_TERMS)
        session.add(row)
    row.permission_state = PERMITTED if permitted else NEEDS_FIRM_TERMS
    row.reference = reference.strip()[:256] or None
    row.recorded_by = actor[:128]
    row.recorded_at_utc = now
    session.flush()
    _audit(
        session,
        actor=actor,
        action="lng_tariff.operator_terms",
        resource=f"lng_terminal_operator:{operator}",
        outcome=row.permission_state,
        detail=f"reference={row.reference}",
        now=now,
    )
    return operator_state(session, operator)


# --- documents -> candidate rows --------------------------------------------------------------


def _parse_from(text: str) -> date | None:
    """An ISO date or "Month YYYY" as the first day it applies; None when not stated."""

    text = (text or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return datetime.strptime(text, "%B %Y").date()
    except ValueError:
        return None


def rows_from_cost(cost, *, document_title: str, retrieved_at: datetime, actor: str) -> list[dict]:
    """Register rows for one parsed ``TerminalCost`` (ingestion/lng_terminal_tariffs.py)."""

    operator = operator_for_terminal(cost.terminal_id) or "unknown"
    base = {
        "terminal_id": cost.terminal_id,
        "operator": operator,
        "terminal_name": cost.name,
        "country": cost.country or None,
        "hub": cost.hub,
        "regime": cost.regime,
        "service": "bundled_slot",
        "product": cost.product,
        "currency": cost.currency,
        "indexation": "cpi_monthly" if cost.regime == "regulated_indexed" else "none",
        "valid_from": _parse_from(cost.effective_from),
        "period_label": (cost.period or cost.effective_from or None),
        "excludes": list(cost.excludes),
        "source_url": cost.source_url,
        "source_sha256": cost.source_sha256,
        "retrieved_at_utc": retrieved_at,
        "document_title": document_title[:256],
        "recorded_by": actor,
    }
    rows: list[dict] = []
    if cost.by_cargo_class:
        rows.append(
            {
                **base,
                "charge_basis": "per_cargo_class",
                "amount": None,
                "unit": f"{cost.currency}/cargo",
                "by_cargo_class": dict(cost.by_cargo_class),
            }
        )
    if cost.fixed_per_cargo:
        rows.append(
            {
                **base,
                "charge_basis": "per_cargo",
                "amount": float(cost.fixed_per_cargo),
                "unit": f"{cost.currency}/cargo",
            }
        )
    if cost.per_mwh:
        rows.append(
            {
                **base,
                "charge_basis": "per_mwh_unloaded",
                "amount": float(cost.per_mwh),
                "unit": f"{cost.currency}/MWh",
            }
        )
    if cost.fuel_retention_pct:
        rows.append(
            {
                **base,
                "charge_basis": "percent_in_kind",
                "amount": float(cost.fuel_retention_pct),
                "unit": "%",
            }
        )
    return rows


def record_document(
    session,
    costs: list,
    *,
    operator: str,
    document_title: str,
    actor: str = "tariff-refresh",
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Add the figures of one operator document as candidates (refused without permission).

    Returns ``{"added": n, "unchanged": bool, "attention": bool}``.
    """

    from eurogas_nexus.db.models import LngTerminalTariffRecord

    if not operator_permitted(session, operator):
        raise TariffRegisterError(
            NEEDS_FIRM_TERMS,
            f"{OPERATOR_TERMS[operator].display_name}: the firm has not recorded permission to "
            "reuse this operator's documents; nothing was read.",
        )
    now = _now(now_utc)
    rows: list[dict] = []
    for cost in costs:
        if operator_for_terminal(cost.terminal_id) != operator:
            raise TariffRegisterError(
                "operator_mismatch", f"{cost.terminal_id} is not a terminal of {operator}.", 422
            )
        rows += rows_from_cost(cost, document_title=document_title, retrieved_at=now, actor=actor)
    digests = {row["source_sha256"] for row in rows}
    known = (
        {
            value
            for (value,) in session.query(LngTerminalTariffRecord.source_sha256)
            .filter(LngTerminalTariffRecord.source_sha256.in_(digests))
            .distinct()
        }
        if digests
        else set()
    )
    fresh = [row for row in rows if row["source_sha256"] not in known]
    if not fresh:
        return {"added": 0, "unchanged": True, "attention": False}
    had_any = (
        session.query(LngTerminalTariffRecord.tariff_id)
        .filter(LngTerminalTariffRecord.operator == operator)
        .first()
        is not None
    )
    for row in fresh:
        session.add(
            LngTerminalTariffRecord(
                tariff_id=f"lngt-{uuid.uuid4().hex[:20]}",
                review_status=CANDIDATE,
                created_at_utc=now,
                by_cargo_class=row.pop("by_cargo_class", None),
                **row,
            )
        )
    session.flush()
    from eurogas_nexus.application.notifications import queue_notification

    name = {"fluxys_lng": "Fluxys LNG", "elengy": "Elengy LNG", "det": "DET LNG"}[operator]
    verb = "changed" if had_any else "published"
    queue_notification(
        session,
        category="tariff",
        severity="medium",
        title=f"{name} tariff {verb}: review {len(fresh)} values",
        body=f"{document_title}\nSource: {fresh[0]['source_url']}",
        dedupe_key=f"lng-tariff-register:{operator}:{sorted(digests)[0]}",
        now=now,
    )
    _audit(
        session,
        actor=actor,
        action="lng_tariff.document",
        resource=f"lng_terminal_operator:{operator}",
        outcome="candidates_added",
        detail=f"rows={len(fresh)}; sha256={sorted(digests)}",
        now=now,
    )
    return {"added": len(fresh), "unchanged": False, "attention": True}


def review_tariff(
    session, tariff_id: str, *, reviewer: str, now_utc: datetime | None = None
) -> dict:
    """Mark a candidate figure reviewed; four eyes: never by whoever recorded it."""

    from eurogas_nexus.db.models import LngTerminalTariffRecord

    row = session.get(LngTerminalTariffRecord, tariff_id)
    if row is None:
        raise TariffRegisterError("tariff_not_found", "No such tariff figure.", 404)
    if row.review_status == REVIEWED:
        return tariff_payload(row)
    if reviewer == row.recorded_by:
        raise TariffRegisterError(
            "four_eyes", "A second person reviews a figure: you recorded this one.", 403
        )
    now = _now(now_utc)
    row.review_status = REVIEWED
    row.reviewed_by = reviewer[:128]
    row.reviewed_at_utc = now
    session.flush()
    _audit(
        session,
        actor=reviewer,
        action="lng_tariff.review",
        resource=f"lng_terminal_tariff:{tariff_id}",
        outcome="reviewed",
        detail=f"terminal={row.terminal_id}; amount={row.amount} {row.unit}",
        now=now,
    )
    from eurogas_nexus.application.opportunities.schedule import note_input_changed

    # A reviewed figure can price an actionable opportunity: an evaluation is due.
    note_input_changed(session, "tariffs", reason=f"tariff {tariff_id} reviewed", at_utc=now)
    return tariff_payload(row)


# --- reads ------------------------------------------------------------------------------------


def tariff_payload(row) -> dict[str, Any]:
    return {
        "tariff_id": row.tariff_id,
        "terminal_id": row.terminal_id,
        "operator": row.operator,
        "terminal_name": row.terminal_name,
        "country": row.country,
        "hub": row.hub,
        "regime": row.regime,
        "service": row.service,
        "product": row.product,
        "charge_basis": row.charge_basis,
        "amount": row.amount,
        "currency": row.currency,
        "unit": row.unit,
        "by_cargo_class": row.by_cargo_class,
        "indexation": row.indexation,
        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
        "valid_to": row.valid_to.isoformat() if row.valid_to else None,
        "period_label": row.period_label,
        "uioli_notice_days": row.uioli_notice_days,
        "uioli_rule": row.uioli_rule,
        "excludes": list(row.excludes or []),
        "source_url": row.source_url,
        "source_sha256": row.source_sha256,
        "retrieved_at_utc": row.retrieved_at_utc.isoformat(),
        "document_title": row.document_title,
        "review_status": row.review_status,
        "recorded_by": row.recorded_by,
        "reviewed_by": row.reviewed_by,
        "reviewed_at_utc": row.reviewed_at_utc.isoformat() if row.reviewed_at_utc else None,
    }


def register_view(session) -> dict[str, Any]:
    from eurogas_nexus.db.models import LngTerminalTariffRecord

    rows = (
        session.query(LngTerminalTariffRecord)
        .order_by(
            LngTerminalTariffRecord.terminal_id, LngTerminalTariffRecord.created_at_utc.desc()
        )
        .all()
    )
    return {
        "operators": [operator_state(session, operator) for operator in OPERATOR_TERMS],
        "tariffs": [tariff_payload(row) for row in rows],
        "counts": {
            "reviewed": sum(row.review_status == REVIEWED for row in rows),
            "candidate": sum(row.review_status == CANDIDATE for row in rows),
            "terminals": len({row.terminal_id for row in rows}),
        },
    }


def public_tariffs(session) -> list[PublicTariff]:
    from eurogas_nexus.db.models import LngTerminalTariffRecord

    return [
        PublicTariff(
            tariff_id=row.tariff_id,
            terminal_id=row.terminal_id,
            product=row.product,
            charge_basis=row.charge_basis,
            amount=row.amount,
            currency=row.currency,
            review_status=row.review_status,
            valid_from=row.valid_from,
            valid_to=row.valid_to,
            by_cargo_class=row.by_cargo_class,
            excludes=tuple(row.excludes or ()),
            source_url=row.source_url,
        )
        for row in session.query(LngTerminalTariffRecord).all()
    ]


def price_terminal(
    session,
    terminal_id: str,
    *,
    arrival_month: str,
    cargo_mwh: float,
    product: str = "spot",
) -> TerminalCharge:
    """Price one cargo at one terminal: firm terms, reviewed, candidate, else the reason."""

    from eurogas_nexus.db.models import LngTerminalTermsRecord
    from eurogas_nexus.domain.portfolio.lng_bid import TerminalTerms

    firm = session.get(LngTerminalTermsRecord, terminal_id)
    firm_terms = None
    if firm is not None and firm.source_url is None:
        # Only terms the desk entered from the firm's own contracts are the firm's terms; rows
        # an earlier tariff refresh wrote from an operator document are not.
        firm_terms = TerminalTerms(
            terminal_id=firm.terminal_id,
            name=firm.name,
            country=firm.country,
            hub=firm.hub,
            currency="EUR" if firm.hub != "NBP" else "GBP",
            regas_tariff_per_mwh=firm.regas_tariff_per_mwh,
            fixed_per_cargo=firm.fixed_per_cargo,
            by_cargo_class=firm.by_cargo_class,
            capacity_basis=firm.capacity_basis,
            variable_regas_per_mwh=firm.variable_regas_per_mwh,
        )
    operator = operator_for_terminal(terminal_id)
    return resolve_terminal_charge(
        terminal_id,
        arrival_month=arrival_month,
        cargo_mwh=cargo_mwh,
        firm_terms=firm_terms,
        public=public_tariffs(session),
        product=product,
        operator_needs_terms=bool(operator) and not operator_permitted(session, operator),
    )


def held_facts(session) -> dict[str, Any]:
    """What the first-run setup guide shows: the public register and the firm's own terms."""

    from eurogas_nexus.db.models import LngTerminalTermsRecord

    view = register_view(session)
    firm = session.query(LngTerminalTermsRecord).count()
    return {
        "terminals_public": view["counts"]["terminals"],
        "reviewed": view["counts"]["reviewed"],
        "candidate": view["counts"]["candidate"],
        "firm_terms": firm,
        "operators_needing_terms": [
            op["display_name"]
            for op in view["operators"]
            if op["permission_state"] == NEEDS_FIRM_TERMS
        ],
    }
