"""Built-in high-value capability handlers (ontology/market/analytics/network)."""

from __future__ import annotations

import math
import statistics
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    CapabilityDefinition,
    CapabilityDomain,
    CapabilityFailureCode,
    CapabilityResult,
    CapabilityStatus,
    DeterminismClass,
    IdempotencyClass,
    SideEffectClass,
)
from eurogas_nexus.domain.research.ontology import (
    CORE_CONCEPTS,
    canonical_entity_id,
)

_KNOWN_HUBS = {
    "TTF": "Title Transfer Facility",
    "NBP": "National Balancing Point",
    "THE": "Trading Hub Europe",
    "PEG": "Point d'Echange de Gaz",
    "ZTP": "Zeebrugge Trading Point",
    "PSV": "Punto di Scambio Virtuale",
}
_KNOWN_INTERCONNECTORS = {
    "BBL": "Bacton-Balgzand pipeline",
    "IUK": "Interconnector UK",
}
_KNOWN_UNITS = {
    "EUR/MWH": {"canonical": "EUR/MWh", "kind": "price"},
    "GBP/MWH": {"canonical": "GBP/MWh", "kind": "price"},
    "MWH": {"canonical": "MWh", "kind": "energy"},
    "MCM/D": {"canonical": "mcm/d", "kind": "flow"},
    "PERCENT": {"canonical": "percent", "kind": "ratio"},
    "DEGC": {"canonical": "degC", "kind": "temperature"},
}


def _result(
    definition: CapabilityDefinition, data: Any, *, warnings: list[str] | None = None
) -> CapabilityResult:
    return CapabilityResult.success(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        data=data,
        warnings=warnings,
    )


def _blocked(
    definition: CapabilityDefinition, code: CapabilityFailureCode, detail: str
) -> CapabilityResult:
    return CapabilityResult.blocked(
        capability=definition.capability_id,
        capability_version=definition.capability_version,
        code=code,
        detail=detail,
    )


def _schema(properties: dict[str, Any], *, required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def _register(
    registry,
    *,
    capability_id: str,
    name: str,
    domain: CapabilityDomain,
    description: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any],
    handler,
    determinism_class: DeterminismClass = DeterminismClass.DETERMINISTIC,
    side_effect_class: SideEffectClass = SideEffectClass.READ_ONLY,
    required_permissions: list[str] | None = None,
    entitlement_policy: str = "none",
    action_policy: ActionPolicy = ActionPolicy.AUTO_ALLOWED,
    tags: list[str] | None = None,
    mcp_name: str | None = None,
    version: str = "v1",
    timeout_policy: str = "30s",
) -> None:
    registry.register(
        CapabilityDefinition(
            capability_id=capability_id,
            name=name,
            domain=domain,
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
            determinism_class=determinism_class,
            side_effect_class=side_effect_class,
            required_permissions=required_permissions or ["capability.invoke"],
            entitlement_policy=entitlement_policy,
            capability_version=version,
            status=CapabilityStatus.ACTIVE,
            owner="research",
            action_policy=action_policy,
            tags=tags or [],
            mcp_name=mcp_name,
            timeout_policy=timeout_policy,
            idempotency=IdempotencyClass.IDEMPOTENT,
        ),
        handler,
    )


def register_core_capabilities(registry) -> None:
    _register_ontology_capabilities(registry)
    _register_analytics_capabilities(registry)
    _register_market_capabilities(registry)
    _register_network_capabilities(registry)
    _register_capacity_capabilities(registry)
    _register_portfolio_capabilities(registry)
    _register_route_capabilities(registry)
    _register_capability_discovery(registry)


def _register_ontology_capabilities(registry) -> None:
    def resolve_entity(arguments, _context):
        definition = registry.get("ontology.resolve_entity")
        source_identifier = str(arguments.get("source_identifier") or "").strip().upper()
        entity_type = str(arguments.get("source_entity_type") or "").strip().lower()
        candidates = list(
            dict.fromkeys([item for item in arguments.get("candidate_identifiers") or [] if item])
        )
        if source_identifier in _KNOWN_HUBS and entity_type in {"", "market_hub", "hub"}:
            return _result(
                definition,
                {
                    "canonical_entity_id": canonical_entity_id("market_hub", source_identifier),
                    "entity_type": "market_hub",
                    "confidence": "CONFIRMED",
                    "display_name": _KNOWN_HUBS[source_identifier],
                },
            )
        if source_identifier in _KNOWN_INTERCONNECTORS and entity_type in {
            "",
            "interconnector",
            "pipeline",
            "infrastructure_asset",
        }:
            return _result(
                definition,
                {
                    "canonical_entity_id": canonical_entity_id("interconnector", source_identifier),
                    "entity_type": "interconnector",
                    "confidence": "CONFIRMED",
                    "display_name": _KNOWN_INTERCONNECTORS[source_identifier],
                },
            )
        if candidates:
            return _result(
                definition,
                {
                    "status": "AMBIGUOUS_ENTITY",
                    "candidates": candidates,
                    "confidence": "LOW",
                },
            )
        return _blocked(
            definition,
            CapabilityFailureCode.ENTITY_NOT_FOUND,
            f"Unknown entity {source_identifier!r}",
        )

    def describe_entity(arguments, _context):
        definition = registry.get("ontology.describe_entity")
        value = str(arguments.get("canonical_entity_id") or "").strip()
        if value.startswith("ent:market_hub:"):
            code = value.rsplit(":", 1)[-1]
            return _result(
                definition,
                {
                    "canonical_entity_id": value,
                    "entity_type": "market_hub",
                    "display_name": _KNOWN_HUBS.get(code, code),
                    "relationships": [
                        {"predicate": "belongs_to", "object": "ent:market_area:" + code},
                        {"predicate": "traded_at", "object": "venue:" + code},
                    ],
                },
            )
        if value.startswith("ent:interconnector:"):
            code = value.rsplit(":", 1)[-1]
            return _result(
                definition,
                {
                    "canonical_entity_id": value,
                    "entity_type": "interconnector",
                    "display_name": _KNOWN_INTERCONNECTORS.get(code, code),
                    "relationships": [],
                },
            )
        return _blocked(definition, CapabilityFailureCode.ENTITY_NOT_FOUND, value)

    def get_relationships(arguments, _context):
        definition = registry.get("ontology.get_relationships")
        concept_id = str(arguments.get("concept_id") or "").strip()
        matches = [concept for concept in CORE_CONCEPTS if concept.concept_id == concept_id]
        return _result(
            definition,
            {
                "concept_id": concept_id,
                "relationships": matches[0].triplets() if matches else [],
            },
        )

    def resolve_product(arguments, _context):
        definition = registry.get("ontology.resolve_product")
        raw = str(arguments.get("product") or "").strip()
        normalized = raw.upper().replace(" ", "_").replace("-", "_")
        supported = normalized in {"DAY_AHEAD", "WITHIN_DAY", "MONTH_AHEAD", "WEEKEND"}
        return _result(
            definition,
            {
                "product": raw,
                "canonical_code": normalized,
                "supported": supported,
                "tenor": normalized.casefold(),
            },
        )

    def resolve_unit(arguments, _context):
        definition = registry.get("ontology.resolve_unit")
        key = str(arguments.get("unit") or "").strip().upper()
        known = _KNOWN_UNITS.get(key)
        if known is None:
            return _blocked(definition, CapabilityFailureCode.INVALID_UNIT, f"Unknown unit {key!r}")
        return _result(definition, {"source_unit": key, **known})

    def series_for_entity(arguments, _context):
        definition = registry.get("ontology.get_series_for_entity")
        hub = str(arguments.get("hub") or "").strip().upper()
        if hub not in _KNOWN_HUBS:
            return _blocked(definition, CapabilityFailureCode.ENTITY_NOT_FOUND, hub)
        return _result(
            definition,
            {
                "series_ids": [
                    f"market.price.{hub}.DAY_AHEAD",
                    f"market.price.{hub}.WITHIN_DAY",
                    f"market.price.{hub}.MONTH_AHEAD",
                ]
            },
        )

    _register(
        registry,
        capability_id="ontology.resolve_entity",
        name="Resolve entity",
        domain=CapabilityDomain.ONTOLOGY,
        description=(
            "Resolve a source identifier to a canonical entity; ambiguity returns candidates."
        ),
        input_schema=_schema(
            {
                "source_id": {"type": "string"},
                "source_entity_type": {"type": "string"},
                "source_identifier": {"type": "string"},
                "candidate_identifiers": {"type": "array", "items": {"type": "string"}},
            },
            required=["source_id", "source_entity_type", "source_identifier"],
        ),
        output_schema={"type": "object"},
        handler=resolve_entity,
        mcp_name="resolve_entity",
    )
    _register(
        registry,
        capability_id="ontology.describe_entity",
        name="Describe entity",
        domain=CapabilityDomain.ONTOLOGY,
        description="Return semantic description and relationships for a canonical entity.",
        input_schema=_schema(
            {"canonical_entity_id": {"type": "string"}}, required=["canonical_entity_id"]
        ),
        output_schema={"type": "object"},
        handler=describe_entity,
        mcp_name="describe_entity",
    )
    _register(
        registry,
        capability_id="ontology.get_relationships",
        name="Get concept relationships",
        domain=CapabilityDomain.ONTOLOGY,
        description="Return typed relationships for one named ontology concept.",
        input_schema=_schema({"concept_id": {"type": "string"}}, required=["concept_id"]),
        output_schema={"type": "object"},
        handler=get_relationships,
    )
    _register(
        registry,
        capability_id="ontology.resolve_product",
        name="Resolve delivery product",
        domain=CapabilityDomain.ONTOLOGY,
        description="Normalize a delivery product/tenor into a canonical code.",
        input_schema=_schema({"product": {"type": "string"}}, required=["product"]),
        output_schema={"type": "object"},
        handler=resolve_product,
        mcp_name="resolve_product",
    )
    _register(
        registry,
        capability_id="ontology.resolve_unit",
        name="Resolve unit",
        domain=CapabilityDomain.ONTOLOGY,
        description="Map a known unit alias to a canonical versioned unit.",
        input_schema=_schema({"unit": {"type": "string"}}, required=["unit"]),
        output_schema={"type": "object"},
        handler=resolve_unit,
    )
    _register(
        registry,
        capability_id="ontology.get_series_for_entity",
        name="Get series for hub",
        domain=CapabilityDomain.ONTOLOGY,
        description="Return canonical market series ids for a known gas hub.",
        input_schema=_schema({"hub": {"type": "string"}}, required=["hub"]),
        output_schema={"type": "object"},
        handler=series_for_entity,
    )


def _register_analytics_capabilities(registry) -> None:
    def _numbers(values: Any, definition) -> list[float] | None:
        try:
            numbers = [float(value) for value in values]
        except (TypeError, ValueError):
            return None
        if len(numbers) < 2:
            return None
        return numbers

    def distribution(arguments, _context):
        definition = registry.get("analytics.distribution")
        numbers = _numbers(arguments.get("values"), definition)
        if numbers is None:
            return _blocked(
                definition,
                CapabilityFailureCode.INSUFFICIENT_HISTORY,
                "values array with >=2 numbers required",
            )
        ordered = sorted(numbers)
        n = len(ordered)

        def quantile(q):
            index = max(0, min(n - 1, int(math.floor(q * (n - 1)))))
            return ordered[index]

        return _result(
            definition,
            {
                "count": n,
                "min": ordered[0],
                "max": ordered[-1],
                "mean": round(statistics.fmean(numbers), 8),
                "median": statistics.median(numbers),
                "std": round(statistics.pstdev(numbers), 8),
                "q05": quantile(0.05),
                "q25": quantile(0.25),
                "q75": quantile(0.75),
                "q95": quantile(0.95),
            },
        )

    def rolling_volatility(arguments, _context):
        definition = registry.get("analytics.rolling_volatility")
        numbers = _numbers(arguments.get("values"), definition)
        window = int(arguments.get("window") or 21)
        if numbers is None or window < 2:
            return _blocked(
                definition, CapabilityFailureCode.INVALID_PRODUCT, "values and window>=2 required"
            )
        result = []
        for index in range(window - 1, len(numbers)):
            result.append(round(statistics.pstdev(numbers[index - window + 1 : index + 1]), 8))
        return _result(
            definition, {"window": window, "volatility": result, "sample_size": len(result)}
        )

    def correlation(arguments, _context):
        definition = registry.get("analytics.correlation")
        x = _numbers(arguments.get("x"), definition)
        y = _numbers(arguments.get("y"), definition)
        if x is None or y is None or len(x) != len(y):
            return _blocked(
                definition,
                CapabilityFailureCode.INVALID_PRODUCT,
                "x/y arrays of equal length >=2 required",
            )
        return _result(definition, {"pearson": round(statistics.correlation(x, y), 8), "n": len(x)})

    def cross_correlation(arguments, _context):
        definition = registry.get("analytics.cross_correlation")
        x = _numbers(arguments.get("x"), definition)
        y = _numbers(arguments.get("y"), definition)
        if x is None or y is None or len(x) != len(y):
            return _blocked(
                definition,
                CapabilityFailureCode.INVALID_PRODUCT,
                "x/y arrays of equal length required",
            )
        max_lag = int(arguments.get("max_lag") or 3)
        lags = []
        for lag in range(-max_lag, max_lag + 1):
            if lag <= 0:
                a, b = x[-lag:], y[:lag] if lag else (x, y)
            else:
                a, b = x[:-lag], y[lag:]
            if len(a) >= 3:
                lags.append({"lag": lag, "correlation": round(statistics.correlation(a, b), 8)})
        return _result(definition, {"lags": lags})

    def zscore(arguments, _context):
        definition = registry.get("analytics.zscore")
        numbers = _numbers(arguments.get("values"), definition)
        if numbers is None:
            return _blocked(
                definition, CapabilityFailureCode.INSUFFICIENT_HISTORY, "values array required"
            )
        mean = statistics.fmean(numbers)
        std = statistics.pstdev(numbers) or 1.0
        return _result(
            definition,
            {
                "mean": round(mean, 8),
                "std": round(std, 8),
                "z": [round((v - mean) / std, 8) for v in numbers],
            },
        )

    def seasonality(arguments, _context):
        definition = registry.get("analytics.seasonality")
        numbers = _numbers(arguments.get("values"), definition)
        period = int(arguments.get("period") or 12)
        if numbers is None or period < 2:
            return _blocked(
                definition, CapabilityFailureCode.INVALID_PRODUCT, "values and period>=2 required"
            )
        buckets = {index: [] for index in range(period)}
        for index, value in enumerate(numbers):
            buckets[index % period].append(value)
        return _result(
            definition,
            {
                "period": period,
                "means": [
                    round(statistics.fmean(buckets[i]), 8) if buckets[i] else None
                    for i in range(period)
                ],
            },
        )

    def event_study(arguments, _context):
        definition = registry.get("analytics.event_study")
        pre = _numbers(arguments.get("pre_event_values"), definition)
        post = _numbers(arguments.get("post_event_values"), definition)
        if pre is None or post is None:
            return _blocked(
                definition, CapabilityFailureCode.INSUFFICIENT_HISTORY, "pre/post arrays required"
            )
        mean_delta = statistics.fmean(post) - statistics.fmean(pre)
        return _result(
            definition,
            {
                "mean_delta": round(mean_delta, 8),
                "pre_n": len(pre),
                "post_n": len(post),
            },
        )

    def regime_summary(arguments, _context):
        definition = registry.get("analytics.regime_summary")
        numbers = _numbers(arguments.get("values"), definition)
        threshold = float(arguments.get("threshold") or 0.0)
        if numbers is None:
            return _blocked(
                definition, CapabilityFailureCode.INSUFFICIENT_HISTORY, "values array required"
            )
        low = [v for v in numbers if v <= threshold]
        high = [v for v in numbers if v > threshold]
        return _result(
            definition,
            {
                "threshold": threshold,
                "low_regime": {
                    "count": len(low),
                    "mean": round(statistics.fmean(low), 8) if low else None,
                },
                "high_regime": {
                    "count": len(high),
                    "mean": round(statistics.fmean(high), 8) if high else None,
                },
            },
        )

    def spread_distribution(arguments, _context):
        definition = registry.get("analytics.spread_distribution")
        left = _numbers(arguments.get("left_values"), definition)
        right = _numbers(arguments.get("right_values"), definition)
        if left is None or right is None or len(left) != len(right):
            return _blocked(
                definition, CapabilityFailureCode.INVALID_PRODUCT, "equal-length arrays required"
            )
        spread = [round(a - b, 8) for a, b in zip(left, right, strict=True)]
        return _result(
            definition,
            {
                "spread": spread,
                "mean": round(statistics.fmean(spread), 8),
                "std": round(statistics.pstdev(spread), 8),
                "n": len(spread),
            },
        )

    number_array = {"type": "array", "items": {"type": "number"}}
    _register(
        registry,
        capability_id="analytics.distribution",
        name="Distribution summary",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute deterministic distribution statistics for a numeric array.",
        input_schema=_schema({"values": number_array}, required=["values"]),
        output_schema={"type": "object"},
        handler=distribution,
        mcp_name="compute_distribution",
    )
    _register(
        registry,
        capability_id="analytics.rolling_volatility",
        name="Rolling volatility",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute bounded rolling standard deviation.",
        input_schema=_schema(
            {"values": number_array, "window": {"type": "integer"}}, required=["values"]
        ),
        output_schema={"type": "object"},
        handler=rolling_volatility,
        mcp_name="compute_rolling_volatility",
    )
    _register(
        registry,
        capability_id="analytics.correlation",
        name="Pearson correlation",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute Pearson correlation for two equal-length arrays.",
        input_schema=_schema({"x": number_array, "y": number_array}, required=["x", "y"]),
        output_schema={"type": "object"},
        handler=correlation,
        mcp_name="compute_correlation",
    )
    _register(
        registry,
        capability_id="analytics.cross_correlation",
        name="Cross correlation",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute lagged cross-correlation within a bounded lag window.",
        input_schema=_schema(
            {"x": number_array, "y": number_array, "max_lag": {"type": "integer"}},
            required=["x", "y"],
        ),
        output_schema={"type": "object"},
        handler=cross_correlation,
        mcp_name="compute_cross_correlation",
    )
    _register(
        registry,
        capability_id="analytics.zscore",
        name="Z-score",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute z-scores against the supplied sample mean/std.",
        input_schema=_schema({"values": number_array}, required=["values"]),
        output_schema={"type": "object"},
        handler=zscore,
    )
    _register(
        registry,
        capability_id="analytics.seasonality",
        name="Seasonality profile",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute period-bucket means without asserting statistical causality.",
        input_schema=_schema(
            {"values": number_array, "period": {"type": "integer"}}, required=["values"]
        ),
        output_schema={"type": "object"},
        handler=seasonality,
    )
    _register(
        registry,
        capability_id="analytics.event_study",
        name="Event study delta",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute mean pre/post difference for supplied event study windows.",
        input_schema=_schema(
            {"pre_event_values": number_array, "post_event_values": number_array},
            required=["pre_event_values", "post_event_values"],
        ),
        output_schema={"type": "object"},
        handler=event_study,
    )
    _register(
        registry,
        capability_id="analytics.regime_summary",
        name="Regime summary",
        domain=CapabilityDomain.ANALYTICS,
        description="Split a sample by an explicit threshold and summarize each regime.",
        input_schema=_schema(
            {"values": number_array, "threshold": {"type": "number"}},
            required=["values", "threshold"],
        ),
        output_schema={"type": "object"},
        handler=regime_summary,
    )
    _register(
        registry,
        capability_id="analytics.spread_distribution",
        name="Spread distribution",
        domain=CapabilityDomain.ANALYTICS,
        description="Compute a deterministic pairwise spread distribution.",
        input_schema=_schema(
            {"left_values": number_array, "right_values": number_array},
            required=["left_values", "right_values"],
        ),
        output_schema={"type": "object"},
        handler=spread_distribution,
        mcp_name="compute_spread_distribution",
    )


def _register_market_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import (
        entitled,
        latest_market_snapshot,
        market_rows,
        session_scope,
    )

    def get_snapshot(arguments, context):
        definition = registry.get("market.get_snapshot")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            payload = latest_market_snapshot(
                session, hub=arguments.get("hub"), product=arguments.get("product")
            )
        payload["rows"] = [
            row for row in payload["rows"] if entitled(context, row["source_system"])
        ]
        return _result(definition, payload)

    def get_history(arguments, context):
        definition = registry.get("market.get_history")
        start = _parse_datetime(arguments.get("start_utc"))
        end = _parse_datetime(arguments.get("end_utc"))
        if start is None or end is None:
            return _blocked(
                definition,
                CapabilityFailureCode.INVALID_PRODUCT,
                "start_utc/end_utc must be ISO-8601 timestamps",
            )
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = market_rows(
                session,
                start_utc=start,
                end_utc=end,
                hub=arguments.get("hub"),
                product=arguments.get("product"),
                limit=int(arguments.get("limit") or 500),
            )
        rows = [row for row in rows if entitled(context, row["source_system"])]
        return _result(definition, {"rows": rows, "count": len(rows)})

    def get_spread(arguments, _context):
        definition = registry.get("market.get_spread")
        origin = float(arguments["origin_value"])
        destination = float(arguments["destination_value"])
        unit = str(arguments.get("unit") or "").strip()
        if not unit:
            return _blocked(definition, CapabilityFailureCode.INVALID_UNIT, "unit required")
        return _result(
            definition,
            {
                "spread_id": (
                    f"{arguments.get('origin_hub')}-{arguments.get('destination_hub')}-{unit}"
                ),
                "origin_hub": arguments.get("origin_hub"),
                "destination_hub": arguments.get("destination_hub"),
                "product": arguments.get("product"),
                "value": round(destination - origin, 8),
                "unit": unit,
                "as_of": datetime.now(UTC).isoformat(),
                "source_evidence": [],
                "freshness": "CALCULATED",
                "quality": "VERIFIED",
            },
        )

    def compare_hubs(arguments, _context):
        definition = registry.get("market.compare_hubs")
        values = arguments.get("hub_values") or []
        if not isinstance(values, list) or not values:
            return _blocked(definition, CapabilityFailureCode.DATA_MISSING, "hub_values required")
        numeric = [float(item.get("value")) for item in values if isinstance(item, dict)]
        if len(numeric) != len(values):
            return _blocked(
                definition, CapabilityFailureCode.INVALID_PRODUCT, "malformed hub_values"
            )
        return _result(
            definition,
            {
                "hubs": values,
                "min": min(numeric),
                "max": max(numeric),
                "spread": round(max(numeric) - min(numeric), 8),
                "n": len(numeric),
            },
        )

    _register(
        registry,
        capability_id="market.get_snapshot",
        name="Market snapshot",
        domain=CapabilityDomain.MARKET,
        description="Return latest entitled market observation per hub/product.",
        input_schema=_schema({"hub": {"type": "string"}, "product": {"type": "string"}}),
        output_schema={"type": "object"},
        handler=get_snapshot,
        entitlement_policy="EEX,Trayport,ICE_OCM,ICIS",
        mcp_name="get_market_snapshot",
    )
    _register(
        registry,
        capability_id="market.get_history",
        name="Market history",
        domain=CapabilityDomain.MARKET,
        description="Return bounded, entitled market observation history.",
        input_schema=_schema(
            {
                "start_utc": {"type": "string"},
                "end_utc": {"type": "string"},
                "hub": {"type": "string"},
                "product": {"type": "string"},
                "limit": {"type": "integer"},
            },
            required=["start_utc", "end_utc"],
        ),
        output_schema={"type": "object"},
        handler=get_history,
        entitlement_policy="EEX,Trayport,ICE_OCM,ICIS",
        mcp_name="get_market_history",
    )
    _register(
        registry,
        capability_id="market.get_spread",
        name="Compute spread",
        domain=CapabilityDomain.MARKET,
        description="Compute a deterministic hub spread from supplied values; no LLM arithmetic.",
        input_schema=_schema(
            {
                "origin_hub": {"type": "string"},
                "destination_hub": {"type": "string"},
                "product": {"type": "string"},
                "origin_value": {"type": "number"},
                "destination_value": {"type": "number"},
                "unit": {"type": "string"},
            },
            required=["origin_hub", "destination_hub", "origin_value", "destination_value", "unit"],
        ),
        output_schema={"type": "object"},
        handler=get_spread,
        mcp_name="compute_hub_spread",
    )
    _register(
        registry,
        capability_id="market.compare_hubs",
        name="Compare hubs",
        domain=CapabilityDomain.MARKET,
        description="Compare supplied hub marks with explicit units/provenance.",
        input_schema=_schema(
            {"hub_values": {"type": "array", "items": {"type": "object"}}}, required=["hub_values"]
        ),
        output_schema={"type": "object"},
        handler=compare_hubs,
        mcp_name="compare_hub_marks",
    )


def _parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _register_network_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import (
        flow_rows,
        session_scope,
    )

    def get_asset(arguments, _context):
        definition = registry.get("network.get_asset")
        node_id = str(arguments.get("asset_id") or "")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.models import (
                ReferenceFacility,
                ReferenceMarketHub,
                ReferenceNode,
            )

            for model in (ReferenceNode, ReferenceFacility, ReferenceMarketHub):
                row = session.get(model, node_id)
                if row is not None:
                    return _result(
                        definition,
                        {
                            "asset_id": node_id,
                            "name": row.name,
                            "asset_type": model.__tablename__,
                            "source_system": getattr(row, "source_system", None),
                            "source_reference": getattr(row, "source_reference", None),
                        },
                    )
        return _blocked(definition, CapabilityFailureCode.ENTITY_NOT_FOUND, node_id)

    def find_path(arguments, _context):
        definition = registry.get("network.find_path")
        source = str(arguments.get("source_node_id") or "")
        target = str(arguments.get("target_node_id") or "")
        edges = arguments.get("edges") or []
        if not edges:
            with session_scope() as session:
                if session is None:
                    return _blocked(
                        definition,
                        CapabilityFailureCode.DATA_MISSING,
                        "edges or runtime DB required",
                    )
                from eurogas_nexus.db.models import ReferenceEdge

                edges = [
                    {"from": row.from_node_id, "to": row.to_node_id}
                    for row in session.query(ReferenceEdge).all()
                ]
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            if isinstance(edge, dict) and edge.get("from") and edge.get("to"):
                adjacency.setdefault(str(edge["from"]), []).append(str(edge["to"]))
                adjacency.setdefault(str(edge["to"]), []).append(str(edge["from"]))
        path = _bfs(adjacency, source, target)
        if path is None:
            return _blocked(
                definition,
                CapabilityFailureCode.ROUTE_BLOCKED,
                f"No path from {source!r} to {target!r}",
            )
        return _result(definition, {"path": path, "length": len(path) - 1})

    def get_flow_context(arguments, _context):
        definition = registry.get("network.get_flow_context")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = flow_rows(session, point_id=arguments.get("point_id"))
        return _result(definition, {"rows": rows, "count": len(rows)})

    def get_storage_context(arguments, _context):
        definition = registry.get("network.get_storage_context")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.models import StorageObservationRecord

            query = session.query(StorageObservationRecord)
            if arguments.get("facility_id"):
                query = query.filter(
                    StorageObservationRecord.facility_id == arguments["facility_id"]
                )
            rows = query.order_by(StorageObservationRecord.observed_at_utc.desc()).limit(100).all()
            payload = [
                {
                    "facility_id": row.facility_id,
                    "working_gas_volume_twh": row.working_gas_volume_twh,
                    "inventory_fill_pct": row.inventory_fill_pct,
                    "observed_at": row.observed_at_utc.isoformat(),
                    "source_system": row.source_system,
                    "source_reference": row.source_reference,
                }
                for row in rows
            ]
        return _result(definition, {"rows": payload, "count": len(payload)})

    def get_lng_context(arguments, _context):
        definition = registry.get("network.get_lng_context")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            from eurogas_nexus.db.models import LngObservationRecord

            query = session.query(LngObservationRecord)
            if arguments.get("terminal_id"):
                query = query.filter(LngObservationRecord.terminal_id == arguments["terminal_id"])
            rows = query.order_by(LngObservationRecord.observed_at_utc.desc()).limit(100).all()
            payload = [
                {
                    "terminal_id": row.terminal_id,
                    "inventory_mcm": row.inventory_mcm,
                    "sendout_mcm_d": row.sendout_mcm_d,
                    "observed_at": row.observed_at_utc.isoformat(),
                    "source_system": row.source_system,
                    "source_reference": row.source_reference,
                }
                for row in rows
            ]
        return _result(definition, {"rows": payload, "count": len(payload)})

    _register(
        registry,
        capability_id="network.get_asset",
        name="Get network asset",
        domain=CapabilityDomain.NETWORK,
        description="Return one canonical reference node/facility/hub.",
        input_schema=_schema({"asset_id": {"type": "string"}}, required=["asset_id"]),
        output_schema={"type": "object"},
        handler=get_asset,
        mcp_name="get_network_asset",
    )
    _register(
        registry,
        capability_id="network.find_path",
        name="Find network path",
        domain=CapabilityDomain.NETWORK,
        description="Find a simple path over supplied or runtime reference edges.",
        input_schema=_schema(
            {
                "source_node_id": {"type": "string"},
                "target_node_id": {"type": "string"},
                "edges": {"type": "array", "items": {"type": "object"}},
            },
            required=["source_node_id", "target_node_id"],
        ),
        output_schema={"type": "object"},
        handler=find_path,
        mcp_name="find_network_path",
    )
    _register(
        registry,
        capability_id="network.get_flow_context",
        name="Get flow context",
        domain=CapabilityDomain.NETWORK,
        description="Return latest physical flow context for a network point.",
        input_schema=_schema({"point_id": {"type": "string"}}),
        output_schema={"type": "object"},
        handler=get_flow_context,
        mcp_name="get_flow_context",
    )
    _register(
        registry,
        capability_id="network.get_storage_context",
        name="Get storage context",
        domain=CapabilityDomain.NETWORK,
        description="Return latest storage inventory context.",
        input_schema=_schema({"facility_id": {"type": "string"}}),
        output_schema={"type": "object"},
        handler=get_storage_context,
        mcp_name="get_storage_context",
    )
    _register(
        registry,
        capability_id="network.get_lng_context",
        name="Get LNG context",
        domain=CapabilityDomain.NETWORK,
        description="Return latest LNG terminal inventory/sendout context.",
        input_schema=_schema({"terminal_id": {"type": "string"}}),
        output_schema={"type": "object"},
        handler=get_lng_context,
        mcp_name="get_lng_context",
    )


def _bfs(adjacency: dict[str, list[str]], source: str, target: str) -> list[str] | None:
    if source == target:
        return [source]
    queue = [[source]]
    seen = {source}
    while queue:
        path = queue.pop(0)
        node = path[-1]
        for neighbor in sorted(adjacency.get(node, [])):
            if neighbor in seen:
                continue
            if neighbor == target:
                return [*path, neighbor]
            seen.add(neighbor)
            queue.append([*path, neighbor])
    return None


def _register_capacity_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import capacity_rows, session_scope

    def get_availability(arguments, _context):
        definition = registry.get("capacity.get_availability")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = capacity_rows(session, point_id=arguments.get("point_id"))
        return _result(definition, {"rows": rows, "count": len(rows)})

    def check_route_feasibility(arguments, _context):
        definition = registry.get("capacity.check_route_feasibility")
        required = float(arguments["required_capacity_mcm_d"])
        available = float(arguments.get("available_capacity_mcm_d") or 0.0)
        blocked = []
        if required > available:
            blocked.append("CAPACITY_UNKNOWN" if available <= 0 else "ROUTE_BLOCKED")
        requested = set(arguments.get("required_tso_access") or [])
        accessible = set(arguments.get("accessible_tsos") or [])
        missing_access = sorted(requested - accessible)
        if missing_access:
            blocked.append("ACCESS_BLOCKED")
        return _result(
            definition,
            {
                "route_name": arguments.get("route_name") or "",
                "required_capacity_mcm_d": required,
                "available_capacity_mcm_d": available,
                "feasible": not blocked and available > 0,
                "blockers": blocked,
                "missing_tso_access": missing_access,
            },
        )

    def get_utilization(arguments, _context):
        definition = registry.get("capacity.get_utilization")
        flow = float(arguments.get("flow_mcm_d") or 0.0)
        capacity = float(arguments.get("capacity_mcm_d") or 0.0)
        if capacity <= 0:
            return _blocked(
                definition,
                CapabilityFailureCode.CAPACITY_UNKNOWN,
                "capacity must be greater than zero",
            )
        return _result(
            definition,
            {
                "flow_mcm_d": flow,
                "capacity_mcm_d": capacity,
                "utilization_pct": round(flow / capacity * 100.0, 4),
            },
        )

    def get_access_state(arguments, _context):
        definition = registry.get("capacity.get_access_state")
        requested = set(arguments.get("required_tso_access") or [])
        accessible = set(arguments.get("accessible_tsos") or [])
        return _result(
            definition,
            {
                "granted": sorted(requested & accessible),
                "missing": sorted(requested - accessible),
                "blocked": bool(requested - accessible),
            },
        )

    _register(
        registry,
        capability_id="capacity.get_availability",
        name="Get capacity availability",
        domain=CapabilityDomain.CAPACITY,
        description="Return latest capacity observations for a network point.",
        input_schema=_schema({"point_id": {"type": "string"}}),
        output_schema={"type": "object"},
        handler=get_availability,
        mcp_name="get_capacity_availability",
    )
    _register(
        registry,
        capability_id="capacity.check_route_feasibility",
        name="Check route feasibility",
        domain=CapabilityDomain.CAPACITY,
        description="Check capacity and TSO access feasibility; unknown capacity blocks.",
        input_schema=_schema(
            {
                "route_name": {"type": "string"},
                "required_capacity_mcm_d": {"type": "number"},
                "available_capacity_mcm_d": {"type": "number"},
                "required_tso_access": {"type": "array", "items": {"type": "string"}},
                "accessible_tsos": {"type": "array", "items": {"type": "string"}},
            },
            required=["required_capacity_mcm_d"],
        ),
        output_schema={"type": "object"},
        handler=check_route_feasibility,
        mcp_name="check_capacity_feasibility",
    )
    _register(
        registry,
        capability_id="capacity.get_utilization",
        name="Get utilization",
        domain=CapabilityDomain.CAPACITY,
        description="Compute flow/capacity utilization from supplied deterministic values.",
        input_schema=_schema(
            {
                "flow_mcm_d": {"type": "number"},
                "capacity_mcm_d": {"type": "number"},
            },
            required=["flow_mcm_d", "capacity_mcm_d"],
        ),
        output_schema={"type": "object"},
        handler=get_utilization,
        mcp_name="compute_capacity_utilization",
    )
    _register(
        registry,
        capability_id="capacity.get_access_state",
        name="Get access state",
        domain=CapabilityDomain.CAPACITY,
        description="Compare required TSO access with the supplied accessible set.",
        input_schema=_schema(
            {
                "required_tso_access": {"type": "array", "items": {"type": "string"}},
                "accessible_tsos": {"type": "array", "items": {"type": "string"}},
            },
            required=["required_tso_access"],
        ),
        output_schema={"type": "object"},
        handler=get_access_state,
        mcp_name="get_tso_access_state",
    )


def _register_portfolio_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import resource_rows, session_scope

    def list_resources(arguments, _context):
        definition = registry.get("portfolio.list_resources")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = resource_rows(session)
        return _result(definition, {"resources": rows, "count": len(rows)})

    def get_resource(arguments, _context):
        definition = registry.get("portfolio.get_resource")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = resource_rows(session, resource_id=arguments.get("resource_id"))
        if not rows:
            return _blocked(
                definition,
                CapabilityFailureCode.ENTITY_NOT_FOUND,
                str(arguments.get("resource_id") or ""),
            )
        return _result(definition, rows[0])

    def get_resource_economics(arguments, _context):
        definition = registry.get("portfolio.get_resource_economics")
        resource_price = float(arguments["resource_price_gbp_mwh"])
        market_price = float(arguments["market_price_gbp_mwh"])
        return _result(
            definition,
            {
                "resource_price_gbp_mwh": resource_price,
                "market_price_gbp_mwh": market_price,
                "indicative_margin_gbp_mwh": round(market_price - resource_price, 8),
                "currency": "GBP",
                "unit": "GBP/MWh",
                "quality": "VERIFIED" if market_price >= resource_price else "OBSERVED",
            },
        )

    def get_relevant_market_dependencies(arguments, _context):
        definition = registry.get("portfolio.get_relevant_market_dependencies")
        hub = str(arguments.get("hub") or "").upper()
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = resource_rows(session)
        relevant = [
            row
            for row in rows
            if hub in str(row.get("delivery_point_name") or "").upper()
            or hub in str(row.get("allowed_exit_points") or "").upper()
        ]
        return _result(
            definition,
            {
                "hub": hub,
                "dependencies": [
                    {
                        "resource_id": row.get("contract_id"),
                        "resource_type": row.get("resource_type"),
                        "delivery_point": row.get("delivery_point_name"),
                        "quantity_mwh_per_day": row.get("delivery_quantity_mwh_per_day"),
                    }
                    for row in relevant
                ],
            },
        )

    _register(
        registry,
        capability_id="portfolio.list_resources",
        name="List portfolio resources",
        domain=CapabilityDomain.PORTFOLIO,
        description="List operator-owned upstream resource contracts.",
        input_schema=_schema({}),
        output_schema={"type": "object"},
        handler=list_resources,
        mcp_name="list_portfolio_resources",
    )
    _register(
        registry,
        capability_id="portfolio.get_resource",
        name="Get resource",
        domain=CapabilityDomain.PORTFOLIO,
        description="Return one upstream resource contract.",
        input_schema=_schema({"resource_id": {"type": "string"}}, required=["resource_id"]),
        output_schema={"type": "object"},
        handler=get_resource,
        mcp_name="get_portfolio_resource",
    )
    _register(
        registry,
        capability_id="portfolio.get_resource_economics",
        name="Get resource economics",
        domain=CapabilityDomain.PORTFOLIO,
        description="Compute deterministic indicative resource margin from supplied prices.",
        input_schema=_schema(
            {
                "resource_price_gbp_mwh": {"type": "number"},
                "market_price_gbp_mwh": {"type": "number"},
            },
            required=["resource_price_gbp_mwh", "market_price_gbp_mwh"],
        ),
        output_schema={"type": "object"},
        handler=get_resource_economics,
        mcp_name="compute_resource_margin",
    )
    _register(
        registry,
        capability_id="portfolio.get_relevant_market_dependencies",
        name="Get relevant market dependencies",
        domain=CapabilityDomain.PORTFOLIO,
        description="Find resources whose delivery/exit points relate to a hub.",
        input_schema=_schema({"hub": {"type": "string"}}, required=["hub"]),
        output_schema={"type": "object"},
        handler=get_relevant_market_dependencies,
        mcp_name="find_market_dependencies",
    )


def _register_route_capabilities(registry) -> None:
    from eurogas_nexus.application.agents.db_bridge import (
        route_candidate_rows,
        session_scope,
    )
    from eurogas_nexus.domain.research.feasibility import (
        FeasibilityInput,
        check_feasibility,
    )
    from eurogas_nexus.domain.research.route_cost import (
        CostComponent,
        RouteCostInput,
        compute_route_cost,
    )

    def find_candidates(arguments, _context):
        definition = registry.get("route.find_candidates")
        with session_scope() as session:
            if session is None:
                return _blocked(
                    definition,
                    CapabilityFailureCode.DATA_MISSING,
                    "Runtime PostgreSQL is not configured",
                )
            rows = route_candidate_rows(session)
        return _result(definition, {"routes": rows, "count": len(rows)})

    def check_feasibility_handler(arguments, _context):
        definition = registry.get("route.check_feasibility")
        output = check_feasibility(
            FeasibilityInput(
                route_name=str(arguments.get("route_name") or ""),
                from_node_id=str(arguments.get("from_node_id") or ""),
                to_node_id=str(arguments.get("to_node_id") or ""),
                capacity_available_mcm_d=float(arguments.get("capacity_available_mcm_d") or 0),
                required_capacity_mcm_d=float(arguments.get("required_capacity_mcm_d") or 0),
                route_eligible=bool(arguments.get("route_eligible", True)),
                contract_active=bool(arguments.get("contract_active", True)),
                constraints=list(arguments.get("constraints") or []),
            )
        )
        return _result(
            definition,
            {
                "status": output.status.value,
                "blockers": output.blockers,
                "conditions": output.conditions,
                "missing_inputs": output.missing_inputs,
                "warnings": output.warnings,
            },
        )

    def calculate_economics(arguments, _context):
        definition = registry.get("route.calculate_economics")
        components = [
            CostComponent(
                component_type=str(item.get("component_type") or "other"),
                amount=float(item.get("amount") or 0),
                unit=str(item.get("unit") or "EUR/MWh"),
                currency=str(item.get("currency") or "EUR"),
                description=str(item.get("description") or ""),
            )
            for item in (arguments.get("components") or [])
        ]
        output = compute_route_cost(
            RouteCostInput(
                route_name=str(arguments.get("route_name") or ""),
                from_node_id=str(arguments.get("from_node_id") or ""),
                to_node_id=str(arguments.get("to_node_id") or ""),
                components=components,
                route_km=(
                    float(arguments["route_km"]) if arguments.get("route_km") is not None else None
                ),
            )
        )
        return _result(
            definition,
            {
                "route_name": output.route_name,
                "total_cost_eur_mwh": output.total_cost_eur_mwh,
                "total_cost_boe": output.total_cost_boe,
                "components": [item.__dict__ for item in output.components],
                "assumptions": output.assumptions,
                "missing_inputs": output.missing_inputs,
                "warnings": output.warnings,
            },
        )

    def explain_constraints(arguments, _context):
        definition = registry.get("route.explain_constraints")
        return _result(
            definition,
            {
                "route_name": arguments.get("route_name"),
                "capacity": arguments.get("capacity"),
                "access": arguments.get("access"),
                "cost_attribution": arguments.get("cost_attribution"),
                "blockers": arguments.get("blockers") or [],
                "evidence": arguments.get("evidence") or [],
            },
        )

    _register(
        registry,
        capability_id="route.find_candidates",
        name="Find route candidates",
        domain=CapabilityDomain.ROUTE,
        description="List active persisted route candidates.",
        input_schema=_schema({}),
        output_schema={"type": "object"},
        handler=find_candidates,
        mcp_name="find_route_candidates",
    )
    _register(
        registry,
        capability_id="route.check_feasibility",
        name="Check route feasibility",
        domain=CapabilityDomain.ROUTE,
        description="Deterministically classify route feasibility from capacity/contract facts.",
        input_schema=_schema(
            {
                "route_name": {"type": "string"},
                "from_node_id": {"type": "string"},
                "to_node_id": {"type": "string"},
                "capacity_available_mcm_d": {"type": "number"},
                "required_capacity_mcm_d": {"type": "number"},
                "route_eligible": {"type": "boolean"},
                "contract_active": {"type": "boolean"},
                "constraints": {"type": "array", "items": {"type": "string"}},
            },
            required=["route_name", "from_node_id", "to_node_id"],
        ),
        output_schema={"type": "object"},
        handler=check_feasibility_handler,
        mcp_name="check_route_feasibility",
    )
    _register(
        registry,
        capability_id="route.calculate_economics",
        name="Calculate route economics",
        domain=CapabilityDomain.ROUTE,
        description="Compute deterministic additive route economics with cost attribution.",
        input_schema=_schema(
            {
                "route_name": {"type": "string"},
                "from_node_id": {"type": "string"},
                "to_node_id": {"type": "string"},
                "route_km": {"type": "number"},
                "components": {"type": "array", "items": {"type": "object"}},
            },
            required=["route_name", "from_node_id", "to_node_id", "components"],
        ),
        output_schema={"type": "object"},
        handler=calculate_economics,
        mcp_name="calculate_route_economics",
    )
    _register(
        registry,
        capability_id="route.explain_constraints",
        name="Explain route constraints",
        domain=CapabilityDomain.ROUTE,
        description="Return structured constraint attribution supplied by deterministic checks.",
        input_schema=_schema(
            {
                "route_name": {"type": "string"},
                "capacity": {"type": "object"},
                "access": {"type": "object"},
                "cost_attribution": {"type": "array", "items": {"type": "object"}},
                "blockers": {"type": "array", "items": {"type": "string"}},
                "evidence": {"type": "array", "items": {"type": "string"}},
            },
            required=["route_name"],
        ),
        output_schema={"type": "object"},
        handler=explain_constraints,
        mcp_name="explain_route_constraints",
    )


def _register_capability_discovery(registry) -> None:
    def list_capabilities(_arguments, _context):
        definition = registry.get("capabilities.list")
        return _result(
            definition,
            {
                "capabilities": [item.public_metadata() for item in registry.list_definitions()],
            },
        )

    def describe_capability(arguments, _context):
        definition = registry.get("capabilities.describe")
        target = registry.get(str(arguments.get("capability_id") or ""))
        if target is None:
            return _blocked(
                definition,
                CapabilityFailureCode.UNKNOWN_CAPABILITY,
                str(arguments.get("capability_id") or ""),
            )
        return _result(definition, target.public_metadata())

    def search_capabilities(arguments, _context):
        definition = registry.get("capabilities.search")
        rows = registry.search(str(arguments.get("query") or ""))
        return _result(
            definition,
            {
                "capabilities": [item.public_metadata() for item in rows],
            },
        )

    _register(
        registry,
        capability_id="capabilities.list",
        name="List capabilities",
        domain=CapabilityDomain.CAPABILITIES,
        description="Discover all active semantic capabilities with metadata.",
        input_schema=_schema({}),
        output_schema={"type": "object"},
        handler=list_capabilities,
        required_permissions=["capability.read"],
        mcp_name="list_capabilities",
    )
    _register(
        registry,
        capability_id="capabilities.describe",
        name="Describe capability",
        domain=CapabilityDomain.CAPABILITIES,
        description="Return one capability contract by id.",
        input_schema=_schema({"capability_id": {"type": "string"}}, required=["capability_id"]),
        output_schema={"type": "object"},
        handler=describe_capability,
        required_permissions=["capability.read"],
        mcp_name="describe_capability",
    )
    _register(
        registry,
        capability_id="capabilities.search",
        name="Search capabilities",
        domain=CapabilityDomain.CAPABILITIES,
        description="Search capabilities by domain/tags/description/input concepts.",
        input_schema=_schema({"query": {"type": "string"}}, required=["query"]),
        output_schema={"type": "object"},
        handler=search_capabilities,
        required_permissions=["capability.read"],
        mcp_name="search_capabilities",
    )
