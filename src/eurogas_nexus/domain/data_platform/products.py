"""Declared Data Product catalogue (Architecture V2 Wave 4).

A Data Product is the *business-facing* data contract defined by
``docs/engineering/Architecture-V2/07_DATA_PLATFORM.md`` section 2: it is
independent of provider implementation, may combine several sources and derived
calculations, and is what users consume - never a provider endpoint
(``02_ARCHITECTURE_CONSTITUTION.md`` rules 11-14).

This module is the single declaration of that catalogue. It is deliberately
pure data plus pure functions:

- every entry names only sources that exist in this repository today
  (``domain/ingestion/source_registry.py``, ``ingestion/connectors``,
  ``ingestion/public_sources.py``) and the endpoint or command that serves it;
- a product whose real implementation does not exist yet is declared with an
  explicit :class:`DataProductAvailability` instead of pretending to exist;
- entitlement is evaluated per principal with the existing fail-closed helpers
  (``domain.dataops.entitlement.derived_result_access``), never re-implemented
  here.

Display rule (07_DATA_PLATFORM.md section 3): this catalogue carries the value
*time basis*, the *as-of*, a *source/provenance summary*, *freshness*,
*quality/confidence* and *entitlement limitations*. It must never carry API
keys, secret values, scheduler internals or retry traces - those belong to the
operator posture in section 4 and are exposed only by the Source Center.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from eurogas_nexus.domain.dataops.entitlement import derived_result_access
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.security.identity import AuthenticatedPrincipal

#: Freshness expectation (minutes) used when a product's declared sources have
#: no per-source expectation of their own. ``None`` means "no cadence is
#: declared anywhere", which must read as NOT_EXPECTED rather than fresh.
NO_DECLARED_EXPECTATION: int | None = None


class TimeBasis(StrEnum):
    """The time basis a Data Product's values are expressed in.

    The basis is part of the contract: two products with different bases must
    never be compared without an explicit conversion, and the gas-day calendar
    version is carried alongside it so a DST-correct read is possible.
    """

    AS_OF_INSTANT = "as_of_instant"
    GAS_DAY = "gas_day"
    DELIVERY_PERIOD = "delivery_period"
    CONTRACT_TERM = "contract_term"


class DataProductAvailability(StrEnum):
    """How much of a declared Data Product exists today.

    The states are deliberately honest rather than aspirational (lowercase to
    match ``SourceDefinition.entitlement_scope``, the other descriptive value in
    a product entry):

    ``AVAILABLE``
        A producer is implemented in this repository and a served surface
        returns its canonical rows.
    ``OPERATOR_INPUT_ONLY``
        The surface is served, but values exist only after an operator-owned
        import or seeding step (no automatic producer).
    ``SIMULATED_ONLY``
        The surface is served from canonical tables, but today only the
        simulated ``*_Sim`` source systems produce rows; the licensed
        connectors are shells pending source certification.
    ``DECLARED_ONLY``
        The endpoint exists and is honest, but no source implementation feeds
        it, so it can only return "not configured" rather than values.
    ``NOT_IMPLEMENTED``
        The product is required by the V2 target and has no served surface at
        all today.
    """

    AVAILABLE = "available"
    OPERATOR_INPUT_ONLY = "operator_input_only"
    SIMULATED_ONLY = "simulated_only"
    DECLARED_ONLY = "declared_only"
    NOT_IMPLEMENTED = "not_implemented"


class DataProductConfidence(StrEnum):
    """Read-side confidence in a product's current provenance.

    Derived only from measured facts (which declared families actually have
    rows, and whether freshness holds), never from a model score. The values use
    the platform's uppercase state vocabulary so they sit consistently beside
    ``FreshnessState`` in the same provenance block.
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class SurfaceKind(StrEnum):
    """What kind of surface serves a Data Product."""

    ENDPOINT = "endpoint"
    MODULE = "module"
    COMMAND = "command"


@dataclass(frozen=True, slots=True)
class ServedSurface:
    """One surface through which a Data Product is reachable today.

    Attributes:
        kind: Endpoint, module or operator command.
        reference: Path, module path or command line.
        description: One-line statement of what the surface returns.
    """

    kind: SurfaceKind
    reference: str
    description: str


@dataclass(frozen=True, slots=True)
class DataProduct:
    """One business-facing Data Product contract.

    Attributes:
        product_id: Stable business identifier; never a provider name.
        business_name: Human name shown to a business user.
        description: What business question the product answers.
        domain: Grouping used by the catalogue read model.
        source_families: Real source families the product derives from today.
        simulated_families: Simulated substitutes that exist in this repository.
        entitlement_families: Families requiring an explicit data entitlement.
            Empty for public-baseline families, which every active principal
            may see (``security.identity.PUBLIC_BASELINE_SOURCE_FAMILIES``).
        time_basis: Time basis of the product's values.
        gas_day_calendar: Versioned gas-day calendar when the basis is a day.
        freshness_expectation_minutes: Declared cadence, or ``None`` when no
            cadence is declared anywhere (which reads as NOT_EXPECTED).
        availability: Explicit state of the implementation today.
        availability_note: Evidence-backed explanation of that state.
        served_by: Surfaces that serve the product today.
        provenance_tables: Canonical runtime tables the product derives from.
        entitlement_note: Extra entitlement fact the family list cannot carry.
    """

    product_id: str
    business_name: str
    description: str
    domain: str
    source_families: tuple[str, ...]
    simulated_families: tuple[str, ...]
    entitlement_families: tuple[str, ...]
    time_basis: TimeBasis
    gas_day_calendar: str | None
    freshness_expectation_minutes: int | None
    availability: DataProductAvailability
    availability_note: str
    served_by: tuple[ServedSurface, ...]
    provenance_tables: tuple[str, ...]
    entitlement_note: str = ""

    @property
    def observed_source_systems(self) -> tuple[str, ...]:
        """Every source system whose rows may contribute to this product."""

        return (*self.source_families, *self.simulated_families)


@dataclass(frozen=True, slots=True)
class ProductEntitlement:
    """Per-principal entitlement verdict for one Data Product.

    Attributes:
        allowed: Whether the principal may see this product's values.
        required_family_count: Declared entitlement families for the product.
        granted_family_count: How many of them the principal is entitled to.
        restricted_family_count: How many are withheld. ``> 0`` means
            ``allowed`` is ``False`` (fail-closed, matching
            ``derived_result_access``: every contributing family must be
            allowed for a derived result to be exposed).
        reason: Stable reason code for the client to render.
        note: Optional non-sensitive explanation from the catalogue.
    """

    allowed: bool
    required_family_count: int
    granted_family_count: int
    restricted_family_count: int
    reason: str
    note: str = ""


def data_products() -> tuple[DataProduct, ...]:
    """Return the declared Data Product catalogue in stable order.

    Returns:
        The catalogue as an immutable tuple; order is the declaration order and
        is stable across calls so clients may diff it.
    """

    return DATA_PRODUCTS


def product_by_id(product_id: str) -> DataProduct | None:
    """Return one declared Data Product by its stable identifier.

    Args:
        product_id: The stable product identifier.

    Returns:
        The product, or ``None`` when the identifier is not declared.
    """

    for product in DATA_PRODUCTS:
        if product.product_id == product_id:
            return product
    return None


def evaluate_product_entitlement(
    principal: AuthenticatedPrincipal,
    product: DataProduct,
) -> ProductEntitlement:
    """Evaluate one product's required families for one principal.

    The check reuses the repository's single fail-closed derived-result policy
    instead of re-implementing family matching: a derived result is exposed only
    when *every* contributing family is allowed. A product with no commercial
    family (public baseline only) is therefore allowed for every active
    principal.

    Args:
        principal: The authenticated principal attached to the request.
        product: The declared product to evaluate.

    Returns:
        The verdict. Restricted families are counted, never echoed: an
        unentitled principal must not learn which licensed family it lacks
        through this surface.
    """

    required = product.entitlement_families
    if not required:
        return ProductEntitlement(
            allowed=True,
            required_family_count=0,
            granted_family_count=0,
            restricted_family_count=0,
            reason="no_commercial_family_required",
            note=product.entitlement_note,
        )
    decision = derived_result_access(principal, required)
    restricted = decision.blocked_sources
    if not restricted:
        return ProductEntitlement(
            allowed=True,
            required_family_count=len(required),
            granted_family_count=len(required),
            restricted_family_count=0,
            reason="entitlement_granted",
            note=product.entitlement_note,
        )
    return ProductEntitlement(
        allowed=False,
        required_family_count=len(required),
        granted_family_count=len(required) - len(restricted),
        restricted_family_count=len(restricted),
        reason="entitlement_restricted",
        note=product.entitlement_note,
    )


def _surface(kind: SurfaceKind, reference: str, description: str) -> ServedSurface:
    """Build one declared served surface (keeps the catalogue readable)."""

    return ServedSurface(kind=kind, reference=reference, description=description)


# ---------------------------------------------------------------------------
# The catalogue
# ---------------------------------------------------------------------------

_AVAILABLE = DataProductAvailability.AVAILABLE
_OPERATOR_INPUT_ONLY = DataProductAvailability.OPERATOR_INPUT_ONLY
_SIMULATED_ONLY = DataProductAvailability.SIMULATED_ONLY
_DECLARED_ONLY = DataProductAvailability.DECLARED_ONLY
_NOT_IMPLEMENTED = DataProductAvailability.NOT_IMPLEMENTED

_EU_CAM = EU_CAM_UTC_CALENDAR

#: The declared catalogue. Each entry is anchored in code that exists:
#:
#: - market context: ``ingestion/simulated_market_prices.py`` (simulated rows)
#:   and the licensed connector shells in ``ingestion/connectors/``;
#: - physical flow / capacity: ``ingestion/public_sources.py`` +
#:   ``scripts/ops/ingest_public_sources.py`` (ENTSOG);
#: - storage / LNG: same ingestion path (GIE AGSI/ALSI, credential-gated);
#: - weather: ``ingestion/connectors/weather.py`` (mock shell) and
#:   ``api/routes/public/weather.py`` (honest empty surface);
#: - portfolio: ``api/routes/internal/portfolio_import.py`` +
#:   ``api/routes/public/portfolio.py``;
#: - route cost inputs: ``domain/route_cost/european_public_tariffs.py``,
#:   ``db/repositories/route_cost.py`` and the ECB FX ingestion path.
DATA_PRODUCTS: tuple[DataProduct, ...] = (
    DataProduct(
        product_id="nbp-day-ahead-market-context",
        business_name="NBP Day-Ahead Market Context",
        description=(
            "GB NBP day-ahead and within-day price context with the venue, tenor, "
            "quality and simulated/licensed origin of every contributing mark."
        ),
        domain="market",
        source_families=("EEX", "ICE_OCM", "Trayport", "ICIS"),
        simulated_families=("EEX_Sim", "ICE_OCM_Sim", "Trayport_Sim", "ICIS_Sim"),
        entitlement_families=("EEX", "ICE_OCM", "Trayport", "ICIS"),
        time_basis=TimeBasis.GAS_DAY,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=1,
        availability=_SIMULATED_ONLY,
        availability_note=(
            "Served from the canonical market tables. Today only the simulated source "
            "systems (EEX_Sim, ICE_OCM_Sim, Trayport_Sim, ICIS_Sim) produce rows: the "
            "licensed connectors exist as shells and a licence-restricted source is "
            "not ingestible until it passes source certification."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/observations",
                "Latest normalized market observations per venue and product.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/quotes",
                "Normalized L1 bid/ask quotes per hub and product.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/stream/quotes",
                "Streaming view over the same normalized quote rows.",
            ),
            _surface(
                SurfaceKind.MODULE,
                "ingestion/simulated_market_prices.py",
                "Simulated EEX/ICE OCM/Trayport-shaped day-ahead and within-day rows.",
            ),
        ),
        provenance_tables=("market_observations", "market_quotes"),
    ),
    DataProduct(
        product_id="ttf-eu-forward-curve-context",
        business_name="TTF / EU Forward Curve Context",
        description=(
            "Forward delivery-period context (month-ahead and further tenors) for TTF "
            "and the other EU hubs, with the assessment and exchange origin of each "
            "curve point."
        ),
        domain="market",
        source_families=("EEX", "ICIS", "Argus", "Platts", "Trayport"),
        simulated_families=("EEX_Sim", "ICIS_Sim", "Trayport_Sim"),
        entitlement_families=("EEX", "ICIS", "Argus", "Platts", "Trayport"),
        time_basis=TimeBasis.DELIVERY_PERIOD,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=1440,
        availability=_SIMULATED_ONLY,
        availability_note=(
            "Served from the canonical market tables using the forward tenors that are "
            "produced today (month-ahead). Only simulated sources produce rows; the "
            "licensed assessment families (ICIS, Argus, Platts) remain connector shells "
            "with no certification, so no licensed curve point exists yet."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/observations",
                "Forward-tenor observation rows with provenance and quality.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/spreads",
                "Backend-computed hub/tenor spreads over those rows.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/quotes",
                "Normalized forward-tenor quotes where a venue publishes them.",
            ),
        ),
        provenance_tables=("market_observations", "market_quotes"),
    ),
    DataProduct(
        product_id="european-physical-flow",
        business_name="European Physical Flow",
        description=(
            "Physical gas flows at ENTSOG interconnection and network points, on the "
            "CAM gas day, with direction and unit normalization."
        ),
        domain="physical",
        source_families=("ENTSOG",),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.GAS_DAY,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=60,
        availability=_AVAILABLE,
        availability_note=(
            "Implemented end to end: public ENTSOG operational data is normalized by "
            "ingestion/public_sources.py and loaded by scripts/ops/ingest_public_sources.py."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/physical/flows",
                "Normalized physical flow observations per point and direction.",
            ),
            _surface(
                SurfaceKind.MODULE,
                "ingestion/public_sources.py",
                "entsog_flow_observations_from_json normalization with unit conversion.",
            ),
            _surface(
                SurfaceKind.COMMAND,
                "python scripts/ops/ingest_public_sources.py --source entsog",
                "Operator-run public ingestion into PostgreSQL.",
            ),
        ),
        provenance_tables=("flow_observations",),
    ),
    DataProduct(
        product_id="capacity-availability",
        business_name="Capacity Availability",
        description=(
            "Technical, booked and available firm/interruptible capacity per point, "
            "direction and capacity product, plus the company's effective TSO access."
        ),
        domain="physical",
        source_families=("ENTSOG",),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.GAS_DAY,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=60,
        availability=_AVAILABLE,
        availability_note=(
            "Implemented from public ENTSOG operational data (capacity indicators) and "
            "the ENTSOG reference network; the operator-owned capacity profiles and TSO "
            "access rows are additional inputs with their own provenance."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/physical/capacity",
                "Normalized capacity observations per point and capacity type.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/reference-network/tso-access",
                "Effective-dated TSO access points and booking platforms.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "POST /api/optimization/capacity",
                "Assessment-only capacity booking over the same capacity inputs.",
            ),
        ),
        provenance_tables=(
            "capacity_observations",
            "reference_nodes",
            "reference_tso_access_points",
        ),
    ),
    DataProduct(
        product_id="storage-context",
        business_name="Storage And LNG Context",
        description=(
            "European storage inventory, working capacity, fill level, injection and "
            "withdrawal, plus LNG terminal inventory and send-out, on the CAM gas day."
        ),
        domain="physical",
        source_families=("GIE",),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.GAS_DAY,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=360,
        availability=_AVAILABLE,
        availability_note=(
            "Implemented from the GIE AGSI (storage) and ALSI (LNG) public APIs. GIE is "
            "a registered credential-gated provider connection, but GIE is a public "
            "baseline entitlement family, so no commercial grant is required to read it; "
            "provider connectivity and user entitlement stay separate concepts."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/storage/observations",
                "Storage inventory and flow observations per facility and gas day.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/storage/sites",
                "Storage facility context derived from the same observations.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/lng/observations",
                "LNG terminal inventory, send-out and DTMI per terminal and gas day.",
            ),
            _surface(
                SurfaceKind.COMMAND,
                "python scripts/ops/ingest_public_sources.py --source gie-agsi",
                "Operator-run GIE ingestion (credential required).",
            ),
        ),
        provenance_tables=("storage_observations", "lng_observations"),
    ),
    DataProduct(
        product_id="weather-context",
        business_name="Weather And Demand Context",
        description=(
            "Temperature, HDD and CDD observations and forecasts used as demand drivers "
            "for storage and route analysis."
        ),
        domain="physical",
        source_families=("Weather",),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.GAS_DAY,
        gas_day_calendar=_EU_CAM,
        freshness_expectation_minutes=180,
        availability=_DECLARED_ONLY,
        availability_note=(
            "Declared but not implemented: /api/weather/* returns an empty list with "
            "WEATHER_SOURCE_NOT_CONFIGURED and the Weather connector is a mock shell. No "
            "weather, HDD or CDD value exists to serve, and the platform must not invent "
            "one. The endpoint surface is honest today; the ingestion path is not."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/weather/observations",
                "Empty until a weather source is ingested (explicit warning).",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/weather/hdd-cdd",
                "Empty until a weather source is ingested (explicit warning).",
            ),
            _surface(
                SurfaceKind.MODULE,
                "ingestion/connectors/weather.py",
                "Mock connector shell; returns empty payloads by default.",
            ),
        ),
        provenance_tables=(),
    ),
    DataProduct(
        product_id="portfolio-position",
        business_name="Portfolio Position",
        description=(
            "Operator-imported order and PnL observations composed into the live "
            "portfolio position and valuation summary."
        ),
        domain="commercial",
        source_families=("operator-input",),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.AS_OF_INSTANT,
        gas_day_calendar=None,
        freshness_expectation_minutes=NO_DECLARED_EXPECTATION,
        availability=_OPERATOR_INPUT_ONLY,
        availability_note=(
            "Served from PostgreSQL, but rows exist only after an operator import "
            "(/api/internal/portfolio/import-observations). No automatic producer exists, "
            "and no cadence is declared, so freshness reads NOT_EXPECTED rather than fresh."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/portfolio/live-summary",
                "Composed live position and valuation summary; nulls when evidence is missing.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/portfolio/pnl-snapshots",
                "Imported PnL snapshots per portfolio and valuation time.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/portfolio/screen-orders",
                "Imported screen orders per venue, hub and product.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/contracts/capacity",
                "Operator-owned capacity profile contracts bound to points.",
            ),
        ),
        provenance_tables=("screen_order_observations", "portfolio_pnl_snapshots"),
        entitlement_note=(
            "Rows enter through the operator-owned internal import and keep the "
            "operator-declared source family of the batch. The read surfaces live under "
            "the declared commercial prefix /api/portfolio/, so a commercial capability "
            "is required independently of the source families listed here."
        ),
    ),
    DataProduct(
        product_id="route-cost-inputs",
        business_name="Route Cost Inputs",
        description=(
            "European TSO capacity tariffs, operator-owned upstream resource contracts, "
            "route candidates and as-of ECB FX needed to cost an explicit-leg route."
        ),
        domain="commercial",
        source_families=(
            "ECB",
            "NationalGasNTS",
            "BBL",
            "IUK",
            "GTS",
            "NaTran",
            "GermanTSO",
            "FluxysBelgium",
            "CNMCEnagas",
            "operator-input",
        ),
        simulated_families=(),
        entitlement_families=(),
        time_basis=TimeBasis.CONTRACT_TERM,
        gas_day_calendar=None,
        freshness_expectation_minutes=43200,
        availability=_OPERATOR_INPUT_ONLY,
        availability_note=(
            "Tariff rows are audited transcriptions of published TSO documents held in "
            "domain/route_cost/*_public_tariffs.py and loaded into tso_tariffs by the "
            "operator seeding/refresh step; upstream resource contracts are operator "
            "upserts; ECB FX is ingested from the public ECB feed. There is no automatic "
            "TSO tariff producer, so the product is operator-input driven."
        ),
        served_by=(
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/route-cost/tso-tariffs",
                "Published TSO tariff rows with document and page provenance.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/route-cost/upstream-contracts",
                "Operator-owned upstream resource contracts used as cost inputs.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/route-cost/route-candidates",
                "Route candidates with legs, capacity limits and TSO requirements.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "/api/market/fx",
                "ECB FX reference rates used for as-of currency conversion.",
            ),
            _surface(
                SurfaceKind.ENDPOINT,
                "POST /api/route-cost/recommend",
                "Decision-support recommendation computed from these inputs.",
            ),
        ),
        provenance_tables=(
            "tso_tariffs",
            "upstream_resource_contracts",
            "capacity_profiles",
            "route_candidates",
            "fx_observations",
        ),
    ),
    DataProduct(
        product_id="lng-cargo-flow-context",
        business_name="LNG Cargo Flow Context",
        description=(
            "Global LNG cargo tracking and voyage context used to anticipate regas "
            "terminal arrivals and send-out pressure."
        ),
        domain="physical",
        source_families=("Kpler",),
        simulated_families=(),
        entitlement_families=("Kpler",),
        time_basis=TimeBasis.AS_OF_INSTANT,
        gas_day_calendar=None,
        freshness_expectation_minutes=NO_DECLARED_EXPECTATION,
        availability=_NOT_IMPLEMENTED,
        availability_note=(
            "Required by the V2 target and declared honestly as not implemented: Kpler "
            "is a registered licensed source with a connector shell only, and no endpoint "
            "serves cargo-level rows. Terminal-level LNG inventory and send-out is served "
            "by the storage-context product instead."
        ),
        served_by=(),
        provenance_tables=(),
    ),
)
