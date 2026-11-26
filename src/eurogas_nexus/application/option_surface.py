"""Read gas option settlements: one source per contract, smile metrics, front-month series.

Order of operations on every read, so a caller never sees more than it is entitled to and a
smile is never stitched from two sources:

1. **Entitlement** first: rows are filtered by the caller's data scopes on their own
   ``source_system`` (``application.projections.market_reads.filter_entitled_rows``). A
   principal without the ICE Endex scope sees neither ICE Endex settlements nor the
   ``ICE_ENDEX_Sim`` demo series.
2. **Precedence** per hub, contract and trade date over what is left:
   exchange settlement > licensed vendor > simulated
   (``domain.market.options.choose_option_source``). The losing sources are reported as
   alternatives, not merged.
3. **Metrics** from the chosen source's rows (``domain.market.options.smile_metrics``).

Front-month ranks (``M1``, ``M2`` ...) count the monthly contracts of a hub whose options
have not expired on the trade date, in delivery order; this is what a constant-maturity
series for a training dataset needs.

读取期权结算价：先授权过滤，再按合约做来源优先级（交易所 > 授权供应商 > 模拟），最后计算微笑指标。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from typing import Any

from eurogas_nexus.domain.market.options import (
    SmileQuote,
    choose_option_source,
    option_source_tier,
    smile_metrics,
)

#: Metrics a series can carry, with their desk unit (``options.<metric>.<hub>.M<n>``).
OPTION_SERIES_METRICS = {
    "atm_iv": ("atm_iv_pct", "%"),
    "rr25": ("rr25_vol_pts", "vol pts"),
    "bf25": ("bf25_vol_pts", "vol pts"),
    "pc_oi_ratio": ("put_call_oi_ratio", "ratio"),
}
MAX_ROWS = 200_000


class OptionHistoryTooLarge(ValueError):
    """More settlement rows than one read may hold; a partial read would bias the metrics."""

    code = "option_history_too_large"
_TIER_NAMES = {0: "exchange", 1: "licensed_vendor", 2: "simulated"}


def option_rows(
    session,
    *,
    hubs: Iterable[str],
    first: date,
    last: date,
    source_systems: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Stored settlements as row dicts (no entitlement applied: the caller filters)."""

    from eurogas_nexus.db.models import OptionSettlementRecord

    query = (
        session.query(OptionSettlementRecord)
        .filter(OptionSettlementRecord.hub.in_(sorted(set(hubs))))
        .filter(OptionSettlementRecord.trade_date >= first)
        .filter(OptionSettlementRecord.trade_date <= last)
    )
    if source_systems is not None:
        query = query.filter(OptionSettlementRecord.source_system.in_(sorted(set(source_systems))))
    # Read one row past the cap: a truncated read would drop whole days or part of a smile
    # and still yield plausible-looking volatilities, so it is refused instead.
    records = query.limit(MAX_ROWS + 1).all()
    if len(records) > MAX_ROWS:
        raise OptionHistoryTooLarge(
            f"more than {MAX_ROWS} option settlements in the range; shorten the period"
        )
    return [
        {
            column: getattr(record, column)
            for column in OptionSettlementRecord.__table__.columns.keys()
        }
        for record in records
    ]


def choose_sources(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, str, date], tuple[str, list[dict[str, Any]], list[dict[str, Any]]]]:
    """Per (hub, contract, trade date): the chosen source, its rows and the alternatives."""

    grouped: dict[tuple[str, str, date], dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in rows:
        grouped[(row["hub"], row["contract"], row["trade_date"])][row["source_system"]].append(row)
    chosen: dict[tuple[str, str, date], tuple[str, list[dict[str, Any]], list[dict[str, Any]]]] = {}
    for key, by_source in grouped.items():
        source = choose_option_source({name: len(items) for name, items in by_source.items()})
        if source is None:
            continue
        alternatives = [
            {
                "source_system": name,
                "tier": _TIER_NAMES.get(option_source_tier(name), "unknown"),
                "rows": len(items),
            }
            for name, items in sorted(by_source.items())
            if name != source
        ]
        chosen[key] = (source, by_source[source], alternatives)
    return chosen


def contract_summary(
    source: str, rows: list[dict[str, Any]], alternatives: list[dict[str, Any]]
) -> dict[str, Any]:
    """One contract's smile and metrics from one source's rows."""

    first = rows[0]
    forward = first.get("underlying_price")
    tenor = (first.get("metadata_json") or {}).get("tenor_years")
    if tenor is None:
        tenor = (first["expiry_date"] - first["trade_date"]).days / 365.0
    quotes = [
        SmileQuote(
            row["strike"], row["option_type"], row.get("implied_vol"), row.get("open_interest")
        )
        for row in rows
    ]
    metrics = (
        smile_metrics(quotes, float(forward), float(tenor)).as_dict()
        if forward and tenor and tenor > 0
        else {
            "atm_iv_pct": None,
            "call_25d_iv_pct": None,
            "put_25d_iv_pct": None,
            "rr25_vol_pts": None,
            "bf25_vol_pts": None,
            "put_call_oi_ratio": None,
            "strikes_used": 0,
            "reasons": {
                "metrics": "expired" if tenor is not None and tenor <= 0 else "no_underlying"
            },
        }
    )
    strikes: dict[float, dict[str, Any]] = {}
    for row in sorted(rows, key=lambda item: (item["strike"], item["option_type"])):
        side = "call" if row["option_type"] == "C" else "put"
        strikes.setdefault(row["strike"], {"strike": row["strike"]})[side] = {
            "settlement": row["settlement_price"],
            "iv_pct": None
            if row.get("implied_vol") is None
            else round(row["implied_vol"] * 100, 4),
            "iv_basis": row.get("iv_basis"),
            "iv_reason": row.get("iv_reason"),
            "delta": row.get("forward_delta"),
            "open_interest": row.get("open_interest"),
            "volume": row.get("volume"),
        }
    simulated = any(row.get("simulated") for row in rows) or source.endswith("_Sim")
    return {
        "hub": first["hub"],
        "contract": first["contract"],
        "trade_date": first["trade_date"].isoformat(),
        "expiry_date": first["expiry_date"].isoformat(),
        "delivery_start_utc": first["delivery_start_utc"].isoformat(),
        "premium_style": first["premium_style"],
        "unit": first["unit"],
        "underlying_price": forward,
        "underlying_basis": first.get("underlying_basis"),
        "tenor_years": tenor,
        "source_system": source,
        "venue": first["venue"],
        "source_tier": _TIER_NAMES.get(option_source_tier(source), "unknown"),
        "simulated": simulated,
        "source_reference": first["source_reference"],
        "ingested_at_utc": max(row["ingested_at_utc"] for row in rows),
        "alternatives": alternatives,
        "metrics": metrics,
        "strikes": list(strikes.values()),
    }


def summaries_by_day(
    rows: Iterable[dict[str, Any]],
) -> dict[tuple[str, date], list[dict[str, Any]]]:
    """Contract summaries per (hub, trade date), ranked M1.. among unexpired monthly contracts."""

    out: dict[tuple[str, date], list[dict[str, Any]]] = defaultdict(list)
    for (hub, _contract, trade_day), (source, items, alternatives) in choose_sources(rows).items():
        summary = contract_summary(source, items, alternatives)
        summary["_kind"] = items[0]["product_kind"]
        summary["_start"] = items[0]["delivery_start_utc"]
        summary["_expired"] = items[0]["expiry_date"] <= trade_day
        out[(hub, trade_day)].append(summary)
    for summaries in out.values():
        summaries.sort(
            key=lambda item: (item["_kind"] != "month", item["_start"], item["contract"])
        )
        rank = 0
        for summary in summaries:
            if summary["_kind"] == "month" and not summary["_expired"]:
                rank += 1
                summary["tenor"] = f"M{rank}"
            else:
                summary["tenor"] = None
            for key in ("_kind", "_start", "_expired"):
                summary.pop(key)
    return out


def metric_series(rows: Iterable[dict[str, Any]], *, hub: str, tenor: str) -> list[dict[str, Any]]:
    """Daily metrics of one hub's ``M<n>`` contract, oldest first."""

    points = []
    for (row_hub, trade_day), summaries in sorted(
        summaries_by_day(rows).items(), key=lambda kv: kv[0][1]
    ):
        if row_hub != hub:
            continue
        for summary in summaries:
            if summary.get("tenor") == tenor:
                points.append(
                    {
                        "trade_date": trade_day.isoformat(),
                        "contract": summary["contract"],
                        "source_system": summary["source_system"],
                        "simulated": summary["simulated"],
                        "underlying_price": summary["underlying_price"],
                        **{
                            key: summary["metrics"][key]
                            for key in (
                                "atm_iv_pct",
                                "rr25_vol_pts",
                                "bf25_vol_pts",
                                "put_call_oi_ratio",
                                "strikes_used",
                            )
                        },
                    }
                )
    return points
