"""Resource-pool composition shared by the route and the projections.

This module is the single home of the portfolio resource/sale-option composition
that ``api/routes/public/route_cost.py`` used to own privately. Both the existing
``GET /api/route-cost/resource-pool/options`` handler and the Wave 5
``PortfolioSnapshot`` projection's ``resources`` slice call it, so the projection
is a composition over the same read instead of a second implementation of the
same queries.

Shape preservation
------------------

:func:`compose_resource_pool_options` returns **exactly** the ``data`` block the
route has always returned (``scope``, ``data_source``, ``portfolio_resources``,
``sale_options``, ``blockers``, ``warnings``). Its private helpers are moved
verbatim, so the route payload stays byte-identical, and the route keeps
compatibility aliases for the test seams the repository already relied on
(``_compose_resource_pool_options``, ``_latest_market_price_by_point``,
``_value_in_gbp``, ``_active_company_tsos``).

Layering
--------

The runtime-database decision and the ``503 runtime_db_unavailable`` translation
stay in the route (HTTP concerns). This module never raises ``HTTPException`` and
keeps SQLAlchemy behind ``TYPE_CHECKING`` plus function-local imports, so
importing the API still does not load the DB layer
(``tests/contract/test_db_foundation.py``).

Entitlement
-----------

The route's own authorisation is unchanged: it composes the rows the runtime
store holds. A read model must never be *wider* than the endpoint it composes, so
:func:`narrow_resource_pool_inputs` re-applies the platform's two declared
fail-closed rules - ``derived_result_access`` for derived route candidates (the
rule ``GET /api/route-cost/route-candidates`` applies) and the source-family row
filter for market observations (the rule ``/api/market/*`` applies) - and reports
what it removed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Any, TypedDict

from pydantic import ValidationError

from eurogas_nexus.domain.dataops.contracts import EntitlementOutcome
from eurogas_nexus.domain.dataops.entitlement import derived_result_access
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.security.identity import AuthenticatedPrincipal

if TYPE_CHECKING:  # pragma: no cover - import boundary: importing the API must not
    # load SQLAlchemy (tests/contract/test_db_foundation.py).
    from sqlalchemy.orm import Session

#: Scope tag of the composed payload (unchanged from the route).
SCOPE = "RESOURCE_POOL_ROUTE_OPTIONS"

#: Provenance label of the read the composition is built from.
DATA_SOURCE = "runtime-postgresql"

#: Entitlement rule labels reported by the projections.
ENTITLEMENT_RULE_DERIVED_AND_SOURCE_FAMILY = (
    "derived route candidates must be fully entitled (derived_result_access) and "
    "market observations must carry a granted source family; the composed route "
    "applies no row-level filter, so this slice is strictly narrower than it"
)
ENTITLEMENT_RULE_LEGACY = "legacy public token keeps the single-trust-domain view"


class ResourcePoolInputs(TypedDict):
    """The six (keyword) inputs :func:`compose_resource_pool_options` consumes."""

    contracts: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    tariffs: list[Any]
    market_rows: list[Any]
    fx_rows: list[Any]
    company_accessible_tsos: list[str] | None


@dataclass(slots=True)
class ResourcePoolEntitlement:
    """What the entitlement narrowing actually removed from the composition."""

    applied: bool
    candidates_in: int
    candidates_kept: int
    market_rows_in: int
    market_rows_kept: int
    rule: str

    @property
    def filtered_out(self) -> int:
        """Total inputs removed by the filter."""

        return max(0, self.candidates_in - self.candidates_kept) + max(
            0, self.market_rows_in - self.market_rows_kept
        )


def read_resource_pool_inputs(
    session: Session,
    *,
    market_limit: int = 2000,
) -> ResourcePoolInputs:
    """Read the rows the resource-pool composition is built from.

    Args:
        session: Open SQLAlchemy session.
        market_limit: Bound on the market-observation read, exactly as the route
            has always applied it.

    Returns:
        The keyword inputs of :func:`compose_resource_pool_options`: upstream
        contracts, route candidates, TSO tariffs, market observations, FX
        observations and the active company TSO access names.
    """

    from eurogas_nexus.db.models import (
        CompanyTsoAccessRecord,
        FxObservationRecord,
    )
    from eurogas_nexus.db.repositories.market_intelligence import (
        list_market_observations_with_source_coverage,
    )
    from eurogas_nexus.db.repositories.route_cost import (
        list_route_candidates,
        list_tso_tariffs,
        list_upstream_contracts,
    )

    contracts = list_upstream_contracts(session)
    candidates = list_route_candidates(session)
    tariffs = list_tso_tariffs(session)
    market_rows = list_market_observations_with_source_coverage(
        session,
        limit=market_limit,
    )
    fx_rows = (
        session.query(FxObservationRecord)
        .order_by(FxObservationRecord.observed_at_utc.desc())
        .all()
    )
    access_rows = (
        session.query(CompanyTsoAccessRecord).order_by(CompanyTsoAccessRecord.tso).all()
    )
    return {
        "contracts": contracts,
        "candidates": candidates,
        "tariffs": tariffs,
        "market_rows": market_rows,
        "fx_rows": fx_rows,
        "company_accessible_tsos": active_company_tsos(access_rows),
    }


def narrow_resource_pool_inputs(
    principal: AuthenticatedPrincipal,
    inputs: ResourcePoolInputs,
) -> tuple[ResourcePoolInputs, ResourcePoolEntitlement]:
    """Apply the platform's fail-closed entitlement rules to composition inputs.

    A sale option is a **derived** result of a route candidate and a market
    observation, so both contributing reads are filtered with the rules their own
    endpoints apply. Operator-owned upstream contracts carry no source system and
    the underlying route applies no filter to them, so they are passed through
    unchanged.

    Args:
        principal: The authenticated principal the read is rendered for.
        inputs: Inputs from :func:`read_resource_pool_inputs`.

    Returns:
        The narrowed inputs and the record of what the filter removed. The
        returned record's ``rule`` names the rule that ran, so a caller can
        state honestly whether any filter applied.
    """

    candidates = list(inputs["candidates"])
    market_rows = list(inputs["market_rows"])
    if principal.auth_method == "legacy_public_token":
        return (
            {**inputs, "candidates": candidates, "market_rows": market_rows},
            ResourcePoolEntitlement(
                applied=False,
                candidates_in=len(candidates),
                candidates_kept=len(candidates),
                market_rows_in=len(market_rows),
                market_rows_kept=len(market_rows),
                rule=ENTITLEMENT_RULE_LEGACY,
            ),
        )

    # Imported here rather than at module scope: the projections package imports
    # this module, and ``row_allowed`` is the one canonical source-family
    # predicate the market reads already use (no second implementation).
    from eurogas_nexus.application.projections.market_reads import row_allowed

    kept_candidates = [
        candidate
        for candidate in candidates
        if derived_result_access(
            principal,
            candidate.get("source_systems") or [],
        ).outcome
        is EntitlementOutcome.ALLOWED
    ]
    kept_market_rows = [
        row for row in market_rows if row_allowed(principal, getattr(row, "source_system", None))
    ]
    return (
        {**inputs, "candidates": kept_candidates, "market_rows": kept_market_rows},
        ResourcePoolEntitlement(
            applied=True,
            candidates_in=len(candidates),
            candidates_kept=len(kept_candidates),
            market_rows_in=len(market_rows),
            market_rows_kept=len(kept_market_rows),
            rule=ENTITLEMENT_RULE_DERIVED_AND_SOURCE_FAMILY,
        ),
    )


def compose_resource_pool_options(
    *,
    contracts: list[dict],
    candidates: list[dict],
    tariffs: list,
    market_rows: list,
    fx_rows: list,
    company_accessible_tsos: list[str] | None = None,
) -> dict:
    """Compose DB-backed portfolio resources and executable sale options.

    The composition is intentionally read-only: it exists so clients do not
    fabricate route options locally when the runtime DB is missing inputs. Every
    step that cannot be verified (market price, TSO access, capacity, FX) fails
    closed and is reported as a blocker or a warning instead of an approximation.

    Args:
        contracts: Upstream resource contracts (``list_upstream_contracts``).
        candidates: Route candidates (``list_route_candidates``).
        tariffs: TSO tariff rows (``list_tso_tariffs``).
        market_rows: Market observation rows, newest first.
        fx_rows: FX observation rows, newest first.
        company_accessible_tsos: Currently active company TSO access names.

    Returns:
        ``{"scope", "data_source", "portfolio_resources", "sale_options",
        "blockers", "warnings"}`` - the payload the route has always returned.
    """

    blockers: list[str] = []
    warnings: list[str] = []
    if not contracts:
        blockers.append("UPSTREAM_CONTRACTS_MISSING")
    if not candidates:
        blockers.append("ROUTE_CANDIDATES_MISSING")

    price_by_point = latest_market_price_by_point(market_rows)
    resources = [
        portfolio_resource_from_contract(
            contract, company_accessible_tsos=company_accessible_tsos
        )
        for contract in contracts
    ]
    sale_options = []
    for candidate in candidates:
        target = str(candidate["target_point_name"]).strip().upper()
        start = str(candidate["start_point_name"]).strip().upper()
        route_topology_kind = route_topology_kind_of(candidate)
        market_price = price_by_point.get(target)
        if market_price is None:
            blockers.append(f"MARKET_PRICE_MISSING:{target}")
            continue

        start_contracts = [
            contract
            for contract in contracts
            if str(contract.get("delivery_point_name") or "").strip().upper() == start
        ]
        if contracts and not start_contracts:
            warnings.append(f"ROUTE_START_NOT_IN_RESOURCE_POOL:{candidate['route_id']}")
            continue
        eligible_contracts = [
            contract
            for contract in start_contracts
            if target == start
            or target
            in {
                str(point).strip().upper()
                for point in contract.get("allowed_exit_points", [])
                if str(point).strip()
            }
        ]
        if contracts and not eligible_contracts:
            warnings.append(f"ROUTE_TARGET_NOT_ALLOWED_BY_CONTRACT:{candidate['route_id']}")
            continue

        route_cost, cost_currency, cost_unit, cost_warnings, cost_blockers = (
            candidate_route_cost(
                candidate,
                tariffs,
                price_currency=market_price["currency"],
                price_unit=market_price["unit"],
                company_accessible_tsos=company_accessible_tsos,
            )
        )
        warnings.extend(cost_warnings)
        blockers.extend(cost_blockers)
        if cost_blockers:
            continue

        capacity_limit = route_capacity_limit(candidate)
        is_cross_zone = (
            str(candidate.get("business_model") or "").upper()
            in {"CROSS_BORDER_TRANSFER", "BORDER_TRANSFER"}
            or start != target
        )
        if capacity_limit is None and is_cross_zone:
            # Cross-zone route with no known capacity: fail closed. Only a
            # same-point sale (NOT_REQUIRED) may proceed without capacity.
            blockers.append(f"ROUTE_CAPACITY_UNKNOWN:{candidate['route_id']}")
            continue
        capacity_status = "KNOWN" if capacity_limit is not None else "NOT_REQUIRED"

        observed_at_iso = market_price["observed_at_utc"]
        asof_date = date_from_iso(observed_at_iso)

        sale_price_gbp, sale_fx_info, sale_fx_warning = value_in_gbp(
            market_price["price"],
            market_price["currency"],
            market_price["unit"],
            asof_date,
            fx_rows,
        )
        if sale_price_gbp is None:
            blockers.append(
                f"MARKET_PRICE_FX_UNAVAILABLE:{target} ({market_price['currency']}->GBP)"
            )
            continue
        if sale_fx_warning:
            warnings.append(f"{sale_fx_warning}:{target}")

        route_cost_gbp, route_fx_info, route_fx_warning = value_in_gbp(
            route_cost,
            cost_currency,
            cost_unit,
            asof_date,
            fx_rows,
        )
        if route_cost_gbp is None:
            blockers.append(
                f"ROUTE_COST_FX_UNAVAILABLE:{candidate['route_id']} ({cost_currency}->GBP)"
            )
            continue
        if route_fx_warning:
            warnings.append(f"{route_fx_warning}:{candidate['route_id']}")

        sale_options.append(
            {
                "option_id": candidate["route_id"],
                "label": candidate["route_name"],
                "delivery_mode": "VIRTUAL_HUB_SALE",
                "target_point_name": candidate["target_point_name"],
                "route_topology_kind": route_topology_kind,
                "sale_price_gbp_mwh": sale_price_gbp,
                "sale_price_currency": "GBP",
                "sale_price_unit": "GBP/MWh",
                "sale_price_source_system": market_price["source_system"],
                "sale_price_source_reference": market_price["source_reference"],
                "sale_price_observed_at_utc": observed_at_iso,
                "sale_price_freshness": market_price["freshness"],
                "sale_price_quality_score": market_price["quality_score"],
                "sale_price_simulated": market_price["simulated"],
                "sale_price_source_family": market_price["source_family"],
                "sale_price_original_currency": market_price["currency"],
                "sale_price_original_unit": market_price["unit"],
                **sale_fx_info,
                "route_cost_gbp_mwh": route_cost_gbp,
                "route_cost_currency": "GBP",
                "route_cost_unit": "GBP/MWh",
                **route_fx_info,
                "capacity_limit_mwh_per_day": capacity_limit,
                "capacity_status": capacity_status,
                "screen_sale_cash_lag_days": screen_cash_lag_days(eligible_contracts),
                "eligible_resource_ids": [
                    contract["contract_id"] for contract in eligible_contracts
                ],
                "required_tso_access": candidate["required_tso_access"],
                "source_refs": [
                    f"route_candidate:{candidate['route_id']}",
                    market_price["source_reference"],
                    *candidate.get("source_systems", []),
                ],
            }
        )

    return {
        "scope": SCOPE,
        "data_source": DATA_SOURCE,
        "portfolio_resources": resources,
        "sale_options": sale_options,
        "blockers": unique(blockers),
        "warnings": unique(warnings),
    }


def latest_market_price_by_point(market_rows: list) -> dict[str, dict]:
    """Return the best market price per point/hub key (see selection priority)."""

    prices: dict[str, dict] = {}
    for row in market_rows:
        keys = market_price_keys(row)
        for key in keys:
            source_system = getattr(row, "source_system", None)
            metadata = row.metadata_json or {}
            simulated = is_simulated_market_price(row)
            candidate = {
                "price": row.price,
                "currency": row.currency,
                "unit": row.unit,
                "source_reference": f"market_observation:{row.observation_id}",
                "source_system": source_system,
                "observed_at_utc": iso_or_none(getattr(row, "observed_at_utc", None)),
                "freshness": getattr(row, "freshness", None),
                "quality_score": getattr(row, "quality_score", None),
                "simulated": simulated,
                "source_family": market_price_source_family(source_system, metadata),
                "selection_priority": market_price_selection_priority(row),
            }
            current = prices.get(key)
            if current is None or candidate["selection_priority"] < current["selection_priority"]:
                prices[key] = candidate
    for price in prices.values():
        price.pop("selection_priority", None)
    return prices


def market_price_keys(row) -> list[str]:
    """Return the point/hub keys one market observation can price."""

    keys = [row.market_venue, row.product]
    metadata = row.metadata_json or {}
    for field in ("hub", "point_name", "market_area"):
        value = metadata.get(field)
        if isinstance(value, str):
            keys.append(value)
    return [value.strip().upper() for value in keys if isinstance(value, str) and value.strip()]


def market_price_basis_priority(row) -> int:
    """Rank a market row's tenor for spot-like resource-pool pricing."""

    metadata = row.metadata_json or {}
    tenor = metadata.get("tenor")
    if not isinstance(tenor, str):
        product = row.product.lower()
        if "within" in product:
            tenor = "within-day"
        elif "day" in product:
            tenor = "day-ahead"
        elif "month" in product:
            tenor = "month-ahead"
        else:
            tenor = ""
    normalized = tenor.strip().lower()
    if normalized in {"day-ahead", "within-day"}:
        return 0
    if normalized in {"weekend", "balance-of-week"}:
        return 1
    if normalized in {"month-ahead", "front-month"}:
        return 2
    return 3


def market_price_selection_priority(row) -> tuple[int, int, int]:
    """Rank rows for spot-like resource-pool pricing.

    The query already orders newest rows first. This priority keeps that order
    for equal candidates while making the two business rules explicit:
    preferred tenors first, licensed/source-provided rows before simulated
    rows, and exchange observations before broker or assessment sources when
    otherwise tied. The source precedence removes dependence on database row
    order for simulator ticks emitted at the same instant.
    """

    return (
        market_price_basis_priority(row),
        1 if is_simulated_market_price(row) else 0,
        market_price_source_priority(getattr(row, "source_system", None)),
    )


def market_price_source_priority(source_system: str | None) -> int:
    """Rank a source system for otherwise-tied market rows."""

    family = (source_system or "").removesuffix("_Sim").upper()
    return {
        "EEX": 0,
        "ICE_OCM": 0,
        "TRAYPORT": 1,
        "ICIS": 2,
    }.get(family, 3)


def is_simulated_market_price(row) -> bool:
    """Whether a market row is simulator-produced rather than source-provided."""

    metadata = row.metadata_json or {}
    if metadata.get("simulated") is True:
        return True
    source_system = getattr(row, "source_system", None)
    return isinstance(source_system, str) and source_system.endswith("_Sim")


def market_price_source_family(
    source_system: str | None,
    metadata: dict,
) -> str | None:
    """Return the entitlement/source family label of a market row."""

    source_family = metadata.get("source_family")
    if isinstance(source_family, str) and source_family.strip():
        return source_family.strip()
    if isinstance(source_system, str) and source_system.endswith("_Sim"):
        return source_system.removesuffix("_Sim")
    return source_system


def iso_or_none(value) -> str | None:
    """Return an ISO string when the value can express one."""

    return value.isoformat() if hasattr(value, "isoformat") else value


def portfolio_resource_from_contract(
    contract: dict, *, company_accessible_tsos: list[str] | None = None
) -> dict:
    """Shape one upstream contract into a portfolio resource payload."""

    resource_type = contract["resource_type"]
    notes = contract_notes_payload(contract.get("notes"))
    variable_cost = non_negative_number(
        contract.get("variable_cost_gbp_mwh", notes.get("variable_cost_gbp_mwh"))
    )
    regas_fee = non_negative_number(
        contract.get("regas_fee_gbp_mwh", notes.get("regas_fee_gbp_mwh"))
    )
    fuel_loss = non_negative_number(
        contract.get("fuel_loss_allowance_pct", notes.get("fuel_loss_allowance_pct"))
    )
    return {
        "resource_id": contract["contract_id"],
        "resource_name": contract["contract_name"],
        "resource_type": resource_type,
        "delivery_mode": (
            "TERMINAL_TITLE_TRANSFER" if resource_type == "LNG_REGAS" else "PHYSICAL_ENTRY_DELIVERY"
        ),
        "location_point_name": contract["delivery_point_name"],
        "available_quantity_mwh_per_day": contract["delivery_quantity_mwh_per_day"],
        "contract_cost_gbp_mwh": contract["contract_price_gbp_mwh"],
        "variable_cost_gbp_mwh": round(variable_cost + regas_fee, 4),
        "fuel_loss_allowance_pct": fuel_loss,
        "delivery_tolerance_pct": contract["delivery_tolerance_pct"],
        "nomination_tolerance_pct": contract["nomination_tolerance_pct"],
        "tolerance_risk_allowance_gbp_mwh": contract.get("tolerance_risk_allowance_gbp_mwh") or 0.0,
        "upstream_payment_lag_days": contract["upstream_payment_lag_days"],
        "screen_sale_cash_lag_days": contract["screen_sale_cash_lag_days"],
        "settlement_frequency": contract["settlement_frequency"],
        "required_tso_access": [],
        "accessible_tsos": list(company_accessible_tsos or []) or None,
        "pricing_method": pricing_method(notes.get("index_basis")),
        "source_refs": unique(
            [
                f"upstream_resource_contract:{contract['contract_id']}",
                *([str(notes["source_reference"])] if notes.get("source_reference") else []),
            ]
        ),
    }


def route_topology_kind_of(candidate: dict) -> str:
    """Separate non-spatial local sales from network transport routes."""

    start = str(candidate.get("start_point_name") or "").strip().upper()
    target = str(candidate.get("target_point_name") or "").strip().upper()
    if start and start == target and not candidate.get("route_legs"):
        return "LOCAL_MARKET_DISPOSITION"
    return "NETWORK_ROUTE"


def contract_notes_payload(value: object) -> dict:
    """Parse the operator notes column into its structured payload."""

    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def non_negative_number(value: object) -> float:
    """Return a non-negative float, or ``0.0`` when the value is not numeric."""

    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0.0
    return max(float(value), 0.0)


def pricing_method(value: object) -> str:
    """Map an operator index basis onto the declared pricing-method vocabulary."""

    normalized = str(value or "").strip().upper()
    if "DAY-AHEAD" in normalized or "DAY AHEAD" in normalized:
        return "DAILY_INDEX"
    if "MONTH" in normalized:
        return "MONTHLY_INDEX"
    if "FIXED" in normalized:
        return "FIXED_PRICE"
    return "OPERATOR_CONTRACT"


def candidate_route_cost(
    candidate: dict,
    tariffs: list,
    *,
    price_currency: str,
    price_unit: str,
    company_accessible_tsos: list[str] | None = None,
) -> tuple[float | None, str | None, str | None, list[str], list[str]]:
    """Cost one route candidate with the shared route-cost engine."""

    if not candidate["route_legs"]:
        return 0.0, None, None, [], []

    try:
        legs = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    except ValidationError:
        return 0.0, None, None, [], [f"ROUTE_LEG_INVALID:{candidate['route_id']}"]

    scenario = RouteCostScenario(
        scenario_id=f"resource-pool-options:{candidate['route_id']}",
        source_resource_type="PIPELINE_IMPORT",
        start_point_id=candidate["start_point_name"],
        target_hub_or_point_id=candidate["target_point_name"],
        business_model="CROSS_BORDER_TRANSFER",
        delivery_mode="BORDER_TRANSFER",
        gas_year=legs[0].gas_year or "2025+",
        capacity_product=legs[0].capacity_product or "ANNUAL",
        firmness=legs[0].firmness or "FIRM",
        required_tso_access=candidate["required_tso_access"],
        company_accessible_tsos=(
            company_accessible_tsos if candidate["required_tso_access"] else None
        ),
        tariff_legs=legs,
    )
    result = calculate_route_cost(scenario, tariffs)
    blockers = [
        *[f"ROUTE_COST_MISSING:{candidate['route_id']}:{item}" for item in result.missing_inputs],
        *[
            f"ROUTE_COST_MISSING:{candidate['route_id']}:{warning}"
            for warning in result.warnings
            if warning == "UNIT_CONVERSION_NOT_IMPLEMENTED"
        ],
    ]
    if result.total_cost is None:
        blockers.append(f"ROUTE_COST_MISSING:{candidate['route_id']}")
        return 0.0, result.currency, result.unit, result.warnings, blockers
    # Currency/unit harmonisation happens downstream in value_in_gbp, which
    # converts both sale price and route cost to GBP/MWh with as-of FX and
    # fails closed when conversion is unavailable.
    return result.total_cost, result.currency, result.unit, result.warnings, blockers


def value_in_gbp(
    value: float | None,
    currency: str | None,
    unit: str | None,
    asof_date: date | None,
    fx_rows: list,
) -> tuple[float | None, dict, str | None]:
    """Convert a value to GBP/MWh with as-of FX provenance (P0-3).

    Values already in GBP pass through unchanged. Non-GBP values are converted
    with FX observations whose value date is not later than ``asof_date``
    (valuation-date as-of join); when no as-of rate exists, the latest rate is
    used and ``fx_as_of_approximated`` is set. Conversion failure returns None
    so callers fail closed.
    """

    if value is None:
        return None, {}, None
    currency_code = (currency or "").strip().upper()
    unit_code = (unit or "").strip().upper()
    if currency_code == "" and value == 0.0:
        # A zero cost carries no currency risk.
        return round(value, 4), {}, None
    if currency_code == "GBP":
        return round(value, 4), {}, None
    if unit_code and not unit_code.endswith("/MWH"):
        return None, {}, None

    asof_rates = fx_rows_as_of(fx_rows, asof_date)
    converted = convert_with_rows(value, currency_code, "GBP", asof_rates)
    approximated = converted is None
    if approximated:
        converted = convert_with_rows(value, currency_code, "GBP", fx_rows)
    if converted is None:
        return None, {}, None

    rate_row = direct_fx_row(fx_rows, currency_code, "GBP", asof_date)
    provenance = {
        "fx_converted_from": currency_code,
        "fx_rate_used": rate_row.rate if rate_row is not None else None,
        "fx_observation_id": rate_row.observation_id if rate_row is not None else None,
        "fx_value_date": rate_row.value_date if rate_row is not None else None,
        "fx_as_of_approximated": approximated,
    }
    warning = f"FX_AS_OF_APPROXIMATED:{currency_code}->GBP" if approximated else None
    return round(converted, 4), provenance, warning


def convert_with_rows(value: float, base: str, quote: str, fx_rows: list) -> float | None:
    """Convert ``value`` from ``base`` to ``quote`` using FX rows as rates.

    Rows are turned into ``FxRateInput`` with ``observed_at_utc`` taken from
    the row's value date, so the shared latest-rate graph picks the latest
    value date within the supplied (already as-of filtered) set.
    """

    from eurogas_nexus.domain.market_intelligence.normalized_view import (
        FxRateInput,
        convert_currency,
    )

    rates = [
        FxRateInput(
            pair=row.pair,
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate=row.rate,
            observed_at_utc=(row.value_date + "T00:00:00+00:00"),
        )
        for row in fx_rows
        if isinstance(row.rate, int | float) and row.rate > 0
    ]
    return convert_currency(value, base, quote, rates)


def fx_rows_as_of(fx_rows: list, asof_date: date | None) -> list:
    """Keep FX rows whose value date is not later than ``asof_date``."""

    if asof_date is None:
        return list(fx_rows)
    return [
        row
        for row in fx_rows
        if fx_value_date(row) is not None and fx_value_date(row) <= asof_date
    ]


def direct_fx_row(fx_rows: list, base: str, quote: str, asof_date: date | None):
    """Return the latest FX row for a direct currency pair (as-of when given)."""

    matches = []
    for row in fx_rows:
        row_base = str(getattr(row, "base_currency", "") or "").strip().upper()
        row_quote = str(getattr(row, "quote_currency", "") or "").strip().upper()
        pair = str(getattr(row, "pair", "") or "").upper()
        if (row_base == base and row_quote == quote) or pair == f"{base}{quote}":
            row_date = fx_value_date(row)
            if asof_date is None or (row_date is not None and row_date <= asof_date):
                matches.append(row)
    if not matches:
        return None
    return max(matches, key=lambda row: fx_value_date(row) or date.min)


def fx_value_date(row) -> date | None:
    """Return an FX row's value date, or ``None`` when it is unusable."""

    value = getattr(row, "value_date", None)
    if isinstance(value, str):
        return date_from_iso(value)
    return None


def date_from_iso(value: str | None) -> date | None:
    """Parse the date part of an ISO string, or ``None``."""

    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def route_capacity_limit(candidate: dict) -> float | None:
    """Return the tightest declared leg capacity of one candidate."""

    capacities = [
        float(leg["available_capacity_mwh_per_day"])
        for leg in candidate.get("route_legs", [])
        if isinstance(leg, dict)
        and isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
    ]
    return min(capacities) if capacities else None


def screen_cash_lag_days(contracts: list[dict]) -> int:
    """Return the shortest screen-sale cash lag among eligible contracts."""

    lags = [
        int(contract["screen_sale_cash_lag_days"])
        for contract in contracts
        if isinstance(contract.get("screen_sale_cash_lag_days"), int)
    ]
    return min(lags) if lags else 1


def active_company_tsos(rows: Sequence[Any]) -> list[str]:
    """Return currently active company TSO access names."""

    now = datetime.now(UTC)
    active: list[str] = []
    for row in rows:
        valid_from = row.valid_from_utc
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=UTC)
        valid_to = row.valid_to_utc
        if valid_to is not None and valid_to.tzinfo is None:
            valid_to = valid_to.replace(tzinfo=UTC)
        if valid_from > now:
            continue
        if valid_to is not None and valid_to < now:
            continue
        if str(row.status).strip().upper() in {"ACTIVE", "CONFIRMED"}:
            active.append(str(row.tso).strip())
    return active


def unique(values: list[str]) -> list[str]:
    """Return values de-duplicated, keeping first-seen order."""

    return list(dict.fromkeys(values))
