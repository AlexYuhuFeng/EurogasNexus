"""The source-precedence resolver against the store: FX rates, interest rates, the order in force.

The domain resolver (``domain/pricing/source_precedence.py``) walks a quantity kind's tiers in
order; this module supplies each tier's lookup from the runtime store and reads the firm's
configured order (organisation setting ``source_precedence``) and banks (organisation setting
``financial_institutions``).

:func:`resolve_fx_rate` is the one entry point every FX conversion uses (LNG-4 included):

    resolve_fx_rate(session, from_ccy, to_ccy, as_of, context="", *, rate_type=None,
                    max_age_days=None, order=None, allowed_systems=None) -> Resolution

* ``from_ccy``, ``to_ccy``: ISO 4217 codes; the value is how many ``to_ccy`` one ``from_ccy``
  buys (``resolve_fx_rate(s, "USD", "EUR", t).value`` converts a USD amount to EUR by
  multiplying).
* ``as_of``: an aware instant. Only rates with a value date on or before its date and
  recorded (``observed_at_utc``) by it are read, so a valuation as of an earlier instant is
  repeatable after later rates arrive.
* ``context``: the calculation asking (``lng_demurrage``, ``route_cost``...). It picks the
  firm's order for ``fx_rate@<context>`` before ``fx_rate``, and the banks configured for it.
* ``rate_type``: ``mid``, ``buy`` or ``sell`` for a bank tier (default: ``mid`` where held,
  otherwise the one held); the reference tiers carry one rate.
* ``max_age_days``: how old the newest fixing may be before the tier is ``stale``; default
  the bank's own ``max_age_days`` for the bank tier, five days for the others.
* ``order``: a calculation's own order, overriding the setting.
* ``allowed_systems``: the source systems the caller is entitled to read (``None``: all).

Tiers (default order): ``contracted_bank`` (rates imported for a configured, contracted bank,
``source_system`` ``BANK:<KEY>``), ``published_reference`` (licensed WM/Reuters or BFIX fixings
held), ``ecb_reference`` (ECB euro reference rates). In each tier the pair is read directly,
inverted, or crossed through EUR from two rates of that same tier. The returned
:class:`~eurogas_nexus.domain.pricing.source_precedence.Resolution` carries the value, the tier
and source used, and every tier tried with why it was skipped.

:func:`resolve_interest_rate` does the same for an interest rate in a currency.

Reads only; nothing is fetched from a bank or anywhere else.

TAR-2：来源优先级解析器的存储层：汇率与利率按企业配置的顺序依次取数，逐层说明采用或跳过原因。
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.pricing import financial_institutions as fi
from eurogas_nexus.domain.pricing import source_precedence as sp

PUBLISHED_REFERENCE_SYSTEMS = ("WMR", "BFIX")
ECB_SYSTEMS = ("ECB",)
DEFAULT_MAX_AGE_DAYS = 5
#: Administrator benchmarks by currency (domain/market/interest_rates.py); €STR is the ECB's.
PUBLISHED_BENCHMARKS = {"GBP": "SONIA", "USD": "SOFR"}
ECB_BENCHMARKS = {"EUR": "ESTR"}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def organisation_setting(session: Any, key: str) -> Any:
    from eurogas_nexus.db.models import OrganisationSettingRecord

    try:
        row = session.get(OrganisationSettingRecord, key)
    except Exception:  # noqa: BLE001 - a store without the table: the defaults hold
        return None
    return None if row is None else row.value_json


def configured_orders(session: Any) -> Mapping[str, Any]:
    value = organisation_setting(session, sp.SETTING)
    return value if isinstance(value, Mapping) else {}


def configured_institutions(session: Any) -> list[fi.Institution]:
    return fi.institutions(organisation_setting(session, fi.SETTING))


def order_in_force(session: Any, kind: str, context: str = "") -> dict[str, Any]:
    """The order a calculation of ``kind`` in ``context`` uses, and where it came from."""

    order, origin = sp.order_for(kind, context, configured_orders(session))
    return {
        "kind": kind,
        "context": context or None,
        "order": list(order),
        "order_source": origin,
        "tiers": [{"tier": tier, "label": sp.TIER_TEXT.get(tier, tier)} for tier in order],
    }


def _banks(session: Any, quantity: str, context: str) -> list[fi.Institution]:
    return [
        bank
        for bank in configured_institutions(session)
        if bank.contracted and bank.applies(quantity, context)
    ]


# --------------------------------------------------------------------------- FX


def _fx_rows(session: Any, systems: Sequence[str], as_of: datetime, currencies: set[str]):
    from eurogas_nexus.db.models import FxObservationRecord as Fx

    return (
        session.query(Fx)
        .filter(Fx.source_system.in_(list(systems)))
        .filter(Fx.value_date <= as_of.date().isoformat())
        .filter(Fx.observed_at_utc <= as_of)
        .filter(Fx.base_currency.in_(sorted(currencies)))
        .filter(Fx.quote_currency.in_(sorted(currencies)))
        .all()
    )


def _latest(rows, base: str, quote: str, rate_type: str | None):
    """The newest rate for ``base``/``quote`` (direct or inverted) among ``rows``."""

    best = None
    for row in rows:
        if {row.base_currency, row.quote_currency} != {base, quote}:
            continue
        if rate_type and row.rate_type in ("mid", "buy", "sell") and row.rate_type != rate_type:
            continue
        preference = 0 if (rate_type or "mid") == row.rate_type else 1
        rank = (row.value_date, -preference, _aware(row.observed_at_utc))
        if best is None or rank > best[0]:
            best = (rank, row)
    if best is None:
        return None
    row = best[1]
    value = row.rate if row.base_currency == base else 1.0 / row.rate
    return value, row


def _fx_lookup(
    session: Any,
    systems: Sequence[str],
    from_ccy: str,
    to_ccy: str,
    as_of: datetime,
    *,
    max_age: int,
    rate_type: str | None,
    label: str,
):
    def lookup() -> sp.Found | sp.Skipped:
        if not systems:
            return sp.Skipped(sp.NOT_CONFIGURED, f"no {label} is configured")
        rows = _fx_rows(session, systems, as_of, {from_ccy, to_ccy, "EUR"})
        if not rows:
            return sp.Skipped(sp.NOT_HELD, f"no {label} rate held by {as_of.date().isoformat()}")
        legs = []
        direct = _latest(rows, from_ccy, to_ccy, rate_type)
        if direct is not None:
            legs, value, method = [direct[1]], direct[0], "direct"
            if direct[1].base_currency != from_ccy:
                method = "inverse"
        elif "EUR" not in (from_ccy, to_ccy):
            first = _latest(rows, from_ccy, "EUR", rate_type)
            second = _latest(rows, "EUR", to_ccy, rate_type)
            if first is None or second is None:
                return sp.Skipped(
                    sp.NOT_COVERING, f"{label}: no {from_ccy}/{to_ccy} rate, direct or via EUR"
                )
            legs, value, method = [first[1], second[1]], first[0] * second[0], "cross_via_eur"
        else:
            return sp.Skipped(sp.NOT_COVERING, f"{label}: no {from_ccy}/{to_ccy} rate")
        oldest = min(date.fromisoformat(row.value_date[:10]) for row in legs)
        if (as_of.date() - oldest).days > max_age:
            return sp.Skipped(
                sp.STALE,
                f"{label}: the newest {from_ccy}/{to_ccy} rate is from {oldest.isoformat()}, "
                f"older than {max_age} days",
            )
        return sp.Found(
            value=value,
            source=" + ".join(dict.fromkeys(row.source_system for row in legs)),
            reference=", ".join(row.observation_id for row in legs),
            as_of=max(row.value_date for row in legs),
            unit=f"{to_ccy}/{from_ccy}",
            detail={
                "method": method,
                "rate_type": legs[0].rate_type,
                "value_dates": [row.value_date for row in legs],
                "pairs": [row.pair for row in legs],
            },
        )

    return lookup


def resolve_fx_rate(
    session: Any,
    from_ccy: str,
    to_ccy: str,
    as_of: datetime,
    context: str = "",
    *,
    rate_type: str | None = None,
    max_age_days: int | None = None,
    order: Sequence[str] | None = None,
    allowed_systems: Collection[str] | None = None,
) -> sp.Resolution:
    """How many ``to_ccy`` one ``from_ccy`` buys as of ``as_of``, by the firm's source order.

    See the module docstring for every argument. ``value`` is ``None`` when no tier holds a
    usable rate; the reasons are in ``tiers``. Never raises for a missing rate.
    """

    source, target = from_ccy.strip().upper(), to_ccy.strip().upper()
    moment = _aware(as_of)
    if rate_type is not None and rate_type not in ("mid", "buy", "sell"):
        raise ValueError("rate_type is mid, buy or sell")
    if source == target:
        found = sp.Found(1.0, "identity", unit=f"{target}/{source}", detail={"method": "same"})
        chosen, origin = sp.order_for(sp.FX_RATE, context, configured_orders(session))
        return sp.Resolution(
            sp.FX_RATE, context, moment, chosen, origin,
            (sp.TierOutcome("same_currency", True, "used", found=found),),
        )

    def allowed(systems: Sequence[str]) -> list[str]:
        if allowed_systems is None:
            return list(systems)
        return [item for item in systems if item in allowed_systems]

    banks = _banks(session, "fx", context)
    bank_age = max_age_days or (min(bank.max_age_days for bank in banks) if banks else 5)
    age = max_age_days or DEFAULT_MAX_AGE_DAYS
    lookups = {
        "contracted_bank": _fx_lookup(
            session, allowed([bank.source_system for bank in banks]), source, target, moment,
            max_age=bank_age, rate_type=rate_type, label="contracted bank",
        ),
        "published_reference": _fx_lookup(
            session, allowed(PUBLISHED_REFERENCE_SYSTEMS), source, target, moment,
            max_age=age, rate_type=None, label="published reference (WM/Reuters, BFIX)",
        ),
        "ecb_reference": _fx_lookup(
            session, allowed(ECB_SYSTEMS), source, target, moment,
            max_age=age, rate_type=None, label="ECB reference",
        ),
    }
    return sp.resolve(
        sp.FX_RATE, lookups, context=context, as_of=moment,
        configured=configured_orders(session), order=order,
    )


# --------------------------------------------------------------------------- interest rates


def _rate_lookup(session: Any, currency: str, as_of: datetime, *, max_age: int, label: str,
                 systems: Sequence[str] | None = None, benchmark: str | None = None):
    def lookup() -> sp.Found | sp.Skipped:
        from eurogas_nexus.db.models import InterestRateObservationRecord as Rate

        if systems is not None and not systems:
            return sp.Skipped(sp.NOT_CONFIGURED, f"no {label} is configured")
        if systems is None and benchmark is None:
            return sp.Skipped(sp.NOT_COVERING, f"{label}: none for {currency}")
        query = (
            session.query(Rate)
            .filter(Rate.currency == currency)
            .filter(Rate.value_date <= as_of.date())
            .filter(Rate.ingested_at_utc <= as_of)
        )
        if systems is not None:
            query = query.filter(Rate.source_system.in_(list(systems)))
        else:
            query = query.filter(Rate.benchmark_id == benchmark)
        row = query.order_by(Rate.value_date.desc(), Rate.benchmark_id).first()
        if row is None:
            return sp.Skipped(sp.NOT_HELD, f"no {label} {currency} rate held")
        if (as_of.date() - row.value_date).days > max_age:
            return sp.Skipped(
                sp.STALE,
                f"{label}: the newest {currency} rate is from {row.value_date.isoformat()}",
            )
        return sp.Found(
            value=row.rate_pct,
            source=row.source_system,
            reference=row.observation_id,
            as_of=row.value_date.isoformat(),
            unit="% a year",
            detail={"benchmark_id": row.benchmark_id, "day_count": row.day_count},
        )

    return lookup


def resolve_interest_rate(
    session: Any,
    currency: str,
    as_of: datetime,
    context: str = "",
    *,
    max_age_days: int | None = None,
    order: Sequence[str] | None = None,
) -> sp.Resolution:
    """The interest rate (percent a year) for ``currency`` as of ``as_of``, by the firm's order:
    its contracted bank's rate, then the administrator's benchmark (SONIA, SOFR), then the
    ECB's €STR for EUR."""

    code = currency.strip().upper()
    moment = _aware(as_of)
    banks = _banks(session, "interest", context)
    age = max_age_days or DEFAULT_MAX_AGE_DAYS
    lookups = {
        "contracted_bank": _rate_lookup(
            session, code, moment, max_age=max_age_days or (
                min(bank.max_age_days for bank in banks) if banks else age
            ),
            label="contracted bank", systems=[bank.source_system for bank in banks],
        ),
        "published_reference": _rate_lookup(
            session, code, moment, max_age=age, label="administrator benchmark",
            benchmark=PUBLISHED_BENCHMARKS.get(code),
        ),
        "ecb_reference": _rate_lookup(
            session, code, moment, max_age=age, label="ECB €STR",
            benchmark=ECB_BENCHMARKS.get(code),
        ),
    }
    return sp.resolve(
        sp.INTEREST_RATE, lookups, context=context, as_of=moment,
        configured=configured_orders(session), order=order,
    )


def fx_converter(session: Any, as_of: datetime, context: str = ""):
    """A ``(amount, from_ccy, to_ccy) -> (value | None, resolution)`` for one calculation."""

    cache: dict[tuple[str, str], sp.Resolution] = {}

    def convert(amount: float, from_ccy: str, to_ccy: str):
        key = (from_ccy.upper(), to_ccy.upper())
        if key not in cache:
            cache[key] = resolve_fx_rate(session, key[0], key[1], as_of, context)
        found = cache[key]
        return (None if found.value is None else amount * found.value), found

    return convert


__all__ = [
    "DEFAULT_MAX_AGE_DAYS",
    "ECB_SYSTEMS",
    "PUBLISHED_REFERENCE_SYSTEMS",
    "configured_institutions",
    "configured_orders",
    "fx_converter",
    "order_in_force",
    "organisation_setting",
    "resolve_fx_rate",
    "resolve_interest_rate",
]

