"""DB-first European route-cost and decision-support endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from eurogas_nexus.api.dependencies.acting_actor import require_acting_actor
from eurogas_nexus.api.dependencies.analysis_snapshot import (
    require_known_analysis_snapshot,
)
from eurogas_nexus.application.resource_pool import (
    active_company_tsos,
    compose_resource_pool_options,
    latest_market_price_by_point,
    read_resource_pool_inputs,
    value_in_gbp,
)
from eurogas_nexus.domain.route_cost.contract_edit_token import (
    CONTRACT_EDIT_CONFLICT,
    CONTRACT_EDIT_TOKEN_MALFORMED,
)
from eurogas_nexus.domain.route_cost.enums import SourceResourceType
from eurogas_nexus.domain.route_cost.lng_regas import (
    LngRegasScenario,
    assess_lng_regas_readiness,
)
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    optimize_resource_pool,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.route_optimizer import (
    RouteRecommendationRequest,
    recommend_route_allocation,
)
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario

router = APIRouter(tags=["route-cost"])

#: Bounded page size for the captured-revision history read: a revision page is
#: immutable economic evidence, so the route serves one bounded, ordered page
#: instead of materializing a contract's whole capture history.
CONTRACT_REVISION_PAGE_DEFAULT_LIMIT = 50
CONTRACT_REVISION_PAGE_MAX_LIMIT = 200

#: Every captured-revision read carries these warnings. A capture is explicit
#: capture-time evidence, not a complete history, and a captured declaration is
#: stored evidence rather than a resolved payment date - the read must say so
#: rather than let a caller infer either.
CONTRACT_REVISION_EVIDENCE_WARNINGS = (
    "Captured revisions are explicit capture-time evidence, not a complete history of past"
    " contract writes.",
    "Captured economics carry, at most, the operator-declared payment terms captured with them"
    " and no effective dates; nothing here asserts when the terms applied or resolves a"
    " payment date.",
)

#: Added to a history page that returned no revision for an existing contract,
#: so "nothing captured yet" is never read as "nothing was read".
CONTRACT_REVISION_EMPTY_WARNING = (
    "No revision has been captured for this contract; an empty page is not evidence that its"
    " terms never changed."
)


class UpstreamContractUpsertRequest(BaseModel):
    """Upsert payload for one operator-owned upstream resource contract.

    Attributes:
        contract_id: Stable contract id (1-128 chars).
        contract_name: Contract display name.
        resource_type: Resource type tag (e.g. ``BEACH_DELIVERY``).
        delivery_point_name: Delivery point name.
        gas_year: Contract gas year.
        delivery_quantity_mwh_per_day: Daily volume (positive).
        contract_price_gbp_mwh: All-in contract price per MWh.
        settlement_frequency: Settlement frequency tag.
        upstream_payment_lag_days: Upstream payment lag (days).
        screen_sale_cash_lag_days: Screen-sale cash lag (days).
        delivery_tolerance_pct / nomination_tolerance_pct: Tolerances.
        tolerance_risk_allowance_gbp_mwh: Risk allowance, or None.
        annual_financing_rate_pct: Financing rate for early-cash value.
        owned_entry_capacity_mwh_per_day / owned_exit_capacity_mwh_per_day:
            Owned capacity, or None.
        allowed_exit_points: Allowed exit points.
        eligible_sale_modes: Eligible sale modes.
        notes: Operator notes, or None.
        payment_terms: Optional strict canonical
            ``contract-payment-terms/v1`` declaration document, or ``None`` to
            clear a stored declaration. Omitted means "preserve the stored
            declaration": presence is read from ``model_fields_set`` so an
            older client that does not know the field never erases it. The
            nested document is validated by the shared strict decoder (not by
            Pydantic), so a malformed declaration is refused with a stable,
            sanitized code and never echoed back. Deliberately untyped here:
            a wrong-typed value must reach the domain refusal, not produce a
            framework validation error that repeats the raw input.
        expected_edit_token: Opaque edit token from a stored-contract read, or
            None for a create-only request. See the write route's docstring.
    """

    contract_id: str = Field(min_length=1, max_length=128)
    contract_name: str = Field(min_length=1, max_length=256)
    resource_type: SourceResourceType
    delivery_point_name: str = Field(min_length=1, max_length=256)
    gas_year: str = Field(min_length=1, max_length=16)
    delivery_quantity_mwh_per_day: float = Field(gt=0)
    contract_price_gbp_mwh: float = Field(ge=0)
    settlement_frequency: str = Field(min_length=1, max_length=32)
    upstream_payment_lag_days: int = Field(ge=0)
    screen_sale_cash_lag_days: int = Field(ge=0)
    delivery_tolerance_pct: float = Field(ge=0)
    nomination_tolerance_pct: float = Field(ge=0)
    tolerance_risk_allowance_gbp_mwh: float | None = Field(default=None, ge=0)
    annual_financing_rate_pct: float = Field(ge=0)
    owned_entry_capacity_mwh_per_day: float | None = Field(default=None, ge=0)
    owned_exit_capacity_mwh_per_day: float | None = Field(default=None, ge=0)
    allowed_exit_points: list[str] = Field(default_factory=list)
    eligible_sale_modes: list[str] = Field(default_factory=list)
    variable_cost_gbp_mwh: float = Field(default=0, ge=0)
    regas_fee_gbp_mwh: float = Field(default=0, ge=0)
    fuel_loss_allowance_pct: float = Field(default=0, ge=0, lt=100)
    notes: str | None = None
    payment_terms: Any = None
    expected_edit_token: str | None = None


@router.get("/api/route-cost/tso-tariffs")
def list_tso_tariffs(
    request: Request,
    country: str | None = None,
    tso: str | None = None,
    market_area: str | None = None,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> dict:
    """Return European TSO tariff rows available to the runtime."""

    tariffs, source, warnings = _load_tariffs()
    filtered = tariffs
    if country:
        filtered = [tariff for tariff in filtered if tariff.country.lower() == country.lower()]
    if tso:
        filtered = [tariff for tariff in filtered if tariff.tso.lower() == tso.lower()]
    if market_area:
        filtered = [
            tariff for tariff in filtered if tariff.market_area.lower() == market_area.lower()
        ]
    if point_name:
        filtered = [
            tariff for tariff in filtered if tariff.source_point_name.lower() == point_name.lower()
        ]
    if direction:
        filtered = [
            tariff for tariff in filtered if tariff.direction.value.lower() == direction.lower()
        ]
    if gas_year:
        filtered = [tariff for tariff in filtered if tariff.gas_year == gas_year]
    return _env(
        {
            "scope": "EUROPEAN_TSO_TARIFFS",
            "data_source": source,
            "tariffs": [tariff.model_dump(mode="json") for tariff in filtered],
        },
        request,
        source=source,
        warnings=warnings,
    )


@router.get("/api/route-cost/route-candidates")
def list_route_candidates(request: Request) -> dict:
    """List route candidates the principal may see (entitlement filtered)."""

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access

    candidates, source, warnings = _load_route_candidates()
    principal = current_principal(request)
    candidates = [
        candidate
        for candidate in candidates
        if derived_result_access(
            principal,
            candidate.get("source_systems") or [],
        ).outcome.value
        == "ALLOWED"
    ]
    return _env(
        {
            "scope": "EUROPEAN_ROUTE_CANDIDATES",
            "data_source": source,
            "route_candidates": candidates,
        },
        request,
        source=source,
        warnings=warnings,
    )


@router.get("/api/route-cost/upstream-contracts")
def list_upstream_contracts(request: Request) -> dict:
    """List DB-backed upstream resource contracts.

    Each payload carries the stored contract fields, the opaque ``edit_token``
    and the strictly decoded declared ``payment_terms`` (the canonical
    ``contract-payment-terms/v1`` document, or ``null`` for "not stated"). A
    stored declaration that fails canonical verification refuses the read with
    a stable, sanitized 409 rather than being served as absent.
    """

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; upstream contracts are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import (
            ContractRevisionPersistenceError,
            list_upstream_contracts,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return _env(
                list_upstream_contracts(session, include_edit_token=True),
                request,
                source="runtime-postgresql",
            )
    except ContractRevisionPersistenceError as exc:
        raise _contract_read_failure(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/route-cost/upstream-contracts")
def upsert_upstream_contract(body: UpstreamContractUpsertRequest, request: Request) -> dict:
    """Persist an upstream resource contract for decision-support workflows.

    治理写入：覆盖前先捕获旧经济状态，覆盖后捕获新经济状态，审计与写入同一事务。

    The write is governed and attributable: the actor is the authenticated
    principal, resolved before any store access and never taken from the body.
    The economic state currently stored is captured as an immutable revision
    *before* it is overwritten and captured again afterwards, so both sides of
    an overwrite are evidence; the captures and the mutation audit commit or
    roll back with the write.

    A write is refused with 409 and changes nothing when the stored terms
    cannot be captured (an unmappable value or ambiguous stored notes):
    overwriting them would destroy the only record of what they were. A replay
    whose economics and display evidence are both identical leaves the source
    row unchanged. If already captured, it adds no revision or audit; otherwise
    it records the first legacy capture and its audit. Existing revision
    attribution is preserved. A change that only touches display evidence
    (contract name, raw operator notes) is audited without allocating a new
    economic revision.

    Stale-edit precondition: ``expected_edit_token`` is the opaque token a
    stored-contract read returned. Omitted or null means **create-only** - an
    existing identity is refused rather than overwritten, and a concurrent
    create that loses the identity race is refused rather than taking over the
    winner's row. A supplied token for an identity with no stored row is
    refused without inserting. A supplied token that no longer matches the
    locked row (a stale read, another writer, or a metadata/notes-only edit) is
    refused with 409 ``contract_edit_conflict`` before any capture, audit or
    mutation; a malformed token is refused with 409
    ``contract_edit_token_malformed`` before any store access. Both refusals
    are stable and sanitized: no stored value, stale payload or commercial
    figure is returned, and there is no overwrite bypass.

    The response keeps every existing field; ``write_outcome`` and
    ``latest_revision`` are additive metadata naming the outcome and the
    contract's newest captured revision, and the stored-contract payloads
    (GET and write response) additionally carry the opaque ``edit_token``. The
    request gains one additive optional field, ``expected_edit_token``: a
    request without it is create-only, never an overwrite.

    Declared payment terms: the request gains one additive optional field,
    ``payment_terms``. Omitted (or sent by a client that does not know it)
    preserves the stored declaration; explicit ``null`` clears it; a strict
    canonical ``contract-payment-terms/v1`` document is validated by the
    shared decoder before any row lock, capture, audit or mutation and stored
    as its own canonical JSON. A declared change is captured as an explicit
    ``upstream-contract-revision/v2`` revision and the response carries the
    decoded declaration; a row whose stored declaration is corrupt fails
    closed on read and write and is never silently cleared. No date is
    resolved and no valuation runs here.

    Honest limits: the token is a bounded stale-edit precondition over the
    single mutable row, not a cryptographic signature and not a lifecycle
    counter, and this is still capture-time evidence rather than a
    draft/frozen revision lifecycle or a complete history before the first
    captured write. The edit-token schema is ``v2`` since this slice added the
    terms carrier to the covered columns: tokens loaded before the upgrade are
    stale by construction, so a client holding one is refused with the
    existing conflict code and must reload the contract - there is no
    fallback. The plain repository
    ``upsert_upstream_contract`` remains an internal compatibility path that
    enforces no token; only this route is the public governed write.
    """

    # The actor is resolved from the authenticated identity before any store
    # access: a caller-supplied name is never trusted (finding C13), and a
    # request with no principal is refused before the write could be attempted.
    principal = require_acting_actor(request)

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "Runtime DB is required to persist upstream resource contracts.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import (
            ContractPaymentTermsRefusal,
            ContractRevisionPersistenceError,
            upsert_upstream_contract_governed,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            try:
                data = body.model_dump(mode="json")
                # Omission preserves the stored declaration; only this field
                # inspects presence, and no global exclude_unset is applied, so
                # every other field keeps its existing replacement semantics.
                if "payment_terms" not in body.model_fields_set:
                    data.pop("payment_terms", None)
                expected_edit_token = data.pop("expected_edit_token", None)
                result = upsert_upstream_contract_governed(
                    session,
                    data,
                    recorded_by=principal.principal_id,
                    recorded_at_utc=datetime.now(UTC),
                    correlation_id=getattr(request.state, "request_id", None),
                    expected_edit_token=expected_edit_token,
                )
            except ContractPaymentTermsRefusal as exc:
                session.rollback()
                raise _contract_terms_refused(exc.code, exc.detail) from exc
            except ContractRevisionPersistenceError as exc:
                session.rollback()
                raise _contract_write_refused(exc.code, exc.detail) from exc
            if result.refused:
                # Fail closed: the stored terms were not captured, so the row
                # keeps them and nothing is committed under this request.
                session.rollback()
                raise _contract_write_refused(result.refusal_code, result.refusal_detail)
            data = {
                **result.contract,
                "human_review_required": True,
                "write_outcome": result.outcome,
                "latest_revision": result.latest_revision,
            }
            session.commit()
            return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/route-cost/upstream-contracts/{contract_id}/revisions")
def list_contract_revisions(
    contract_id: str,
    request: Request,
    limit: int = Query(
        default=CONTRACT_REVISION_PAGE_DEFAULT_LIMIT,
        ge=1,
        le=CONTRACT_REVISION_PAGE_MAX_LIMIT,
    ),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List one contract's captured economic revisions, oldest number first.

    Reads the immutable capture evidence the governed write path stores - the
    same verified repository read the write response cites - and never captures
    anything itself: a read of a changed source row adds no revision and no
    audit row. An unknown contract is 404 ``upstream_contract_not_found``; an
    existing contract with nothing captured answers an empty, bounded page with
    ``revision_count`` 0 and an explicit warning, so "no captures yet" is
    never confused with "no such contract" or with an unread store.

    ``limit``/``offset`` page the revision-number order and are pushed into the
    query, so a contract with a long capture record materializes one bounded
    page of snapshot evidence rather than its whole history.

    Honest limits, carried as warnings: a captured revision is explicit
    capture-time evidence of the row as the capture read it - not a complete
    history before the first captured write - and it holds no payment terms or
    effective dates.
    """

    if not _db_is_configured():
        raise _runtime_db_required("read captured contract revisions")

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import (
            ContractRevisionPersistenceError,
            count_upstream_contract_revisions,
            list_upstream_contract_revisions,
            upstream_contract_exists,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            if not upstream_contract_exists(session, contract_id):
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": "not_found",
                        "code": "upstream_contract_not_found",
                        "message": f"No upstream contract is stored for {contract_id!r}.",
                    },
                )
            revision_count = count_upstream_contract_revisions(session, contract_id)
            revisions = list_upstream_contract_revisions(
                session,
                contract_id,
                limit=limit,
                offset=offset,
            )
    except ContractRevisionPersistenceError as exc:
        raise _contract_revision_read_failure(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    warnings = list(CONTRACT_REVISION_EVIDENCE_WARNINGS)
    if revision_count == 0:
        warnings.append(CONTRACT_REVISION_EMPTY_WARNING)
    data = {
        "scope": "UPSTREAM_CONTRACT_REVISIONS",
        "data_source": "runtime-postgresql",
        "contract_id": contract_id,
        "revision_count": revision_count,
        "returned_count": len(revisions),
        "has_more": offset + len(revisions) < revision_count,
        "limit": limit,
        "offset": offset,
        "revisions": revisions,
    }
    return _env(data, request, source="runtime-postgresql", warnings=warnings)


@router.get(
    "/api/route-cost/upstream-contracts/{contract_id}/revisions/{contract_revision_id}"
)
def get_contract_revision(
    contract_id: str,
    contract_revision_id: str,
    request: Request,
) -> dict:
    """Read one captured revision, explicitly scoped to its contract.

    The revision id is only answered under the contract it was captured for: a
    revision that belongs to a different contract is refused with the same 404
    ``contract_revision_not_found`` as an unknown id, so the surface never
    confirms that a revision exists under a contract the caller did not name.
    The evidence row is verified by the existing repository read (reviewed
    capture origin, stored hash, canonical decode and matching contract id and
    schema version) before it is served.

    An integrity-verification failure is a structured 409 carrying the
    repository's stable code and a fixed message only: stored row content,
    driver messages and SQL are never echoed. The response preserves the
    capture origin, schema version, content hash, capture instant and original
    recorder, and carries the same honest-limit warnings as the history read.
    """

    if not _db_is_configured():
        raise _runtime_db_required("read a captured contract revision")

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import (
            ContractRevisionPersistenceError,
            get_upstream_contract_revision,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            revision = get_upstream_contract_revision(
                session,
                contract_revision_id,
                contract_id=contract_id,
            )
    except ContractRevisionPersistenceError as exc:
        raise _contract_revision_read_failure(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    data = {
        **revision,
        "scope": "UPSTREAM_CONTRACT_REVISION",
        "data_source": "runtime-postgresql",
    }
    return _env(
        data,
        request,
        source="runtime-postgresql",
        warnings=CONTRACT_REVISION_EVIDENCE_WARNINGS,
    )


@router.get("/api/route-cost/resource-pool/options")
def get_resource_pool_options(request: Request) -> dict:
    """Compose DB-backed portfolio resources and executable sale options.

    This endpoint is intentionally read-only. It exists so clients do not
    fabricate route options locally when the runtime DB is missing inputs.

    The composition itself lives in
    :mod:`eurogas_nexus.application.resource_pool`, so the Wave 5
    ``PortfolioSnapshot`` projection composes the identical payload from the same
    read instead of duplicating it (Architecture V2 Wave 5 follow-up).
    """

    if not _db_is_configured():
        data = {
            "scope": "RESOURCE_POOL_ROUTE_OPTIONS",
            "data_source": "runtime-db-not-configured",
            "portfolio_resources": [],
            "sale_options": [],
            "blockers": ["RUNTIME_DB_NOT_CONFIGURED"],
            "warnings": [],
        }
        return _env(
            data,
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; resource-pool options are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            data = compose_resource_pool_options(**read_resource_pool_inputs(session))
        return _env(data, request, source="runtime-postgresql", warnings=data["warnings"])
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/route-cost/calculate")
def post_route_cost_calculation(body: RouteCostScenario, request: Request) -> dict:
    """Calculate a European explicit-leg route-cost scenario."""

    tariffs, source, warnings = _load_tariffs()
    calculation = calculate_route_cost(body, tariffs)
    return _env(
        calculation.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *calculation.warnings],
    )


@router.post("/api/route-cost/recommend")
def post_route_recommendation(body: RouteRecommendationRequest, request: Request) -> dict:
    """Recommend route and sale-market allocation using runtime tariff rows.

    When the caller supplies an ``analysis_snapshot_id`` (Architecture V2 Wave 4)
    the reference is verified against persisted Analysis Snapshots before the run
    and echoed on the result, so a produced recommendation cites the snapshot it
    was computed against instead of carrying an unverified string.
    """

    _require_known_analysis_snapshot(body.analysis_snapshot_id)
    tariffs, source, warnings = _load_tariffs()
    recommendation = recommend_route_allocation(body, tariffs)
    return _env(
        recommendation.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *recommendation.warnings],
    )


@router.post("/api/route-cost/lng-regas/assess")
def post_lng_regas_assessment(body: LngRegasScenario, request: Request) -> dict:
    """Assess LNG regas terminal access, slot, delivery mode, and pricing readiness."""

    result = assess_lng_regas_readiness(body)
    return _env(
        result.model_dump(mode="json"),
        request,
        source="operator-input",
        warnings=result.warnings,
    )


@router.post("/api/route-cost/resource-pool/optimize")
def post_resource_pool_optimization(
    body: PortfolioOptimizationScenario,
    request: Request,
) -> dict:
    """Optimize multi-upstream resource-pool allocation across selling options.

    The scenario must carry an explicit finite ``annual_financing_rate_pct``
    (percent per year) for the early-cash term: the optimiser holds no default,
    so omission, ``null``, booleans, strings, ``NaN`` or ±infinity are refused
    as request validation errors (422) instead of being priced from an
    undeclared assumption. An explicit ``0`` is a recorded zero.

    Payment/sale lags are declared inputs as well: every resource must carry an
    explicit ``upstream_payment_lag_days`` and every sale option an explicit
    ``screen_sale_cash_lag_days`` (whole non-negative days, or an explicit
    ``null`` for unknown). The previous implicit ``20``/``1`` day defaults are
    removed; a pair whose effective sale-cash lag stays unknown (no resource
    override and no option declaration) is refused and reported as a missing
    input instead of receiving an assumed receipt day.

    When the caller supplies an ``analysis_snapshot_id`` (Architecture V2 Wave 4)
    the reference is verified against persisted Analysis Snapshots before the run
    and echoed on the result, so a produced allocation cites the version set it
    was computed against instead of carrying an unverified string.

    Architecture V2 Wave 8: the run is tracked under the shared job lifecycle, so
    ``/api/jobs`` shows what the deployment actually optimised, against which
    snapshot, and with a stable code when it fails. Tracking never changes what
    this handler returns or raises.

    **This operation has two public routes** (register C14/D8). This one uniquely verifies and
    echoes an Analysis Snapshot and tracks the run as a job, and is the route the product calls;
    ``POST /api/optimization/resource-pool`` uniquely supports the runtime/DB-first decision
    context. This route stays canonical until the other carries these same two invariants: see
    ``W0-03`` D8.
    """

    _require_known_analysis_snapshot(body.analysis_snapshot_id)

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.jobs import run_tracked_job

    def _optimize(handle) -> dict:
        # A pure computation persists no artefact, so the job records the
        # snapshot it cites and its inputs; there is no output reference to
        # invent. ``add_output`` is the seam the day this result is persisted.
        result = optimize_resource_pool(body)
        payload = result.model_dump(mode="json")
        if body.analysis_snapshot_id:
            payload["analysis_snapshot_id"] = body.analysis_snapshot_id
        else:
            # A caller that cites no snapshot keeps the previous payload exactly:
            # the reference is additive and appears only when it carries a value.
            payload.pop("analysis_snapshot_id")
        return payload

    payload = run_tracked_job(
        _optimize,
        kind="OPTIMISATION",
        principal=current_principal(request).name,
        scope_refs=(f"PORTFOLIO:{body.portfolio_id}",),
        snapshot_id=body.analysis_snapshot_id or "",
        inputs=body.model_dump(mode="json"),
        correlation_id=getattr(request.state, "request_id", None),
        provenance=("route-cost-resource-pool",),
    )
    return _env(
        payload,
        request,
        source="operator-input",
        warnings=payload["warnings"],
    )


def _require_known_analysis_snapshot(snapshot_id: str | None) -> None:
    """Verify a supplied Analysis Snapshot reference (compatibility alias).

    The check itself lives in
    :mod:`eurogas_nexus.api.dependencies.analysis_snapshot`, so every run path
    that accepts an optional ``analysis_snapshot_id`` refuses an unknown
    reference with the same status codes and error codes.
    """

    require_known_analysis_snapshot(snapshot_id)


def _load_tariffs():
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["No runtime DB configured; European TSO tariff rows are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_tso_tariffs(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _load_route_candidates() -> tuple[list[dict], str, list[str]]:
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["No runtime DB configured; route candidates are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_route_candidates
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_route_candidates(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


# --- Application-layer seams (Architecture V2 Wave 5 follow-up) -------------
#
# The composition below now lives in
# ``eurogas_nexus.application.resource_pool``, so the PortfolioSnapshot
# projection's ``resources`` slice composes the identical payload from the same
# read instead of duplicating it. The private names stay as compatibility
# aliases for the repository's existing test seams, exactly as ``market.py``
# keeps ``_market_row`` / ``_fx_row``.


def _compose_resource_pool_options(
    *,
    contracts: list[dict],
    candidates: list[dict],
    tariffs: list,
    market_rows: list,
    fx_rows: list,
    company_accessible_tsos: list[str] | None = None,
) -> dict:
    """Compose portfolio resources and sale options (compatibility alias)."""

    return compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=tariffs,
        market_rows=market_rows,
        fx_rows=fx_rows,
        company_accessible_tsos=company_accessible_tsos,
    )


def _latest_market_price_by_point(market_rows: list) -> dict[str, dict]:
    """Return the selected market price per point (compatibility alias)."""

    return latest_market_price_by_point(market_rows)


def _value_in_gbp(
    value: float | None,
    currency: str | None,
    unit: str | None,
    asof_date,
    fx_rows: list,
) -> tuple[float | None, dict, str | None]:
    """Convert a value to GBP/MWh with as-of FX provenance (compatibility alias)."""

    return value_in_gbp(value, currency, unit, asof_date, fx_rows)


def _active_company_tsos(rows: list) -> list[str]:
    """Return currently active company TSO access names (compatibility alias)."""

    return active_company_tsos(rows)


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for route-cost reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _runtime_db_required(action: str) -> HTTPException:
    """503 refusal when a read that must be verified has no runtime store.

    Captured revisions are evidence: without the runtime database there is
    nothing to verify, so the read refuses instead of answering an empty page
    that could be mistaken for "nothing was captured".
    """

    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_not_configured",
            "message": f"Runtime DB is required to {action}.",
        },
    )


def _contract_revision_read_failure(exc: Exception) -> HTTPException:
    """Stable, sanitized refusal for a revision read that cannot be served.

    A missing revision - including a revision id scoped to a different
    contract - is 404 ``contract_revision_not_found``, the same code and
    message for both, so the surface never confirms that a revision exists
    under a contract the caller did not name. Any other repository refusal is
    an integrity-verification failure: 409 with the stable code and a fixed
    message, never stored row content, driver text or SQL.
    """

    code = getattr(exc, "code", None) or "contract_revision_read_refused"
    if code == "contract_revision_not_found":
        return HTTPException(
            status_code=404,
            detail={
                "error": "not_found",
                "code": code,
                "message": "No captured contract revision matches this contract and revision id.",
            },
        )
    return HTTPException(
        status_code=409,
        detail={
            "error": "conflict",
            "code": code,
            "message": (
                "The stored contract revision failed immutable-evidence verification,"
                " so it was refused rather than served."
            ),
        },
    )


def _contract_read_failure(exc: Exception) -> HTTPException:
    """Stable, sanitized refusal for a stored-contract read that failed closed.

    The failed read here is a stored payment-terms declaration that is not a
    canonical document: serving the row would present corruption as "no terms
    stated", so the whole read refuses with the repository's stable code and a
    fixed message. Stored text, driver messages and SQL are never echoed, and
    the malformed declaration is preserved in storage for a separate
    remediation step.
    """

    code = getattr(exc, "code", None) or "contract_read_refused"
    return HTTPException(
        status_code=409,
        detail={
            "error": "conflict",
            "code": code,
            "message": (
                "The stored contract could not be read: its stored payment terms"
                " failed canonical verification, so the row was refused rather"
                " than served with the declaration treated as absent."
            ),
        },
    )


def _contract_terms_refused(code: str, detail: str) -> HTTPException:
    """Stable, sanitized refusal for a supplied payment-terms declaration.

    The declaration is validated by the shared strict decoder *before* the row
    lock, any capture, audit or mutation, so a refused write changes nothing.
    The code is the decoder's own stable code and the reason is the decoder's
    sanitized detail (fixed schema labels, safe item indices/counts and stable
    codes only - never a supplied value, field name or repr), so a malformed
    nested document is not echoed back to the caller.
    """

    return HTTPException(
        status_code=422,
        detail={
            "error": code,
            "message": (
                "The contract was not written: the supplied payment terms are not"
                " a strict canonical contract-payment-terms document. Nothing was"
                " changed."
            ),
            "reason": detail,
        },
    )


def _contract_write_refused(code: str | None, detail: str | None) -> HTTPException:
    """Stable refusal for a governed contract write that failed closed.

    Two families share the 409 status and are deliberately distinct:

    * an edit-precondition failure (``contract_edit_conflict`` /
      ``contract_edit_token_malformed``) answers one fixed, sanitized message:
      the caller must read the stored contract again and reconcile; no stored
      value, stale payload or commercial figure is echoed.
    * a capture failure (the stored terms could not be captured as immutable
      evidence) names the capture code a client can act on, in the catalogued
      ``conflict`` family; overwriting those terms could destroy the only
      record of what they were, so nothing changes.
    """

    if code in (CONTRACT_EDIT_CONFLICT, CONTRACT_EDIT_TOKEN_MALFORMED):
        message = (
            "The contract was not written: the supplied edit token is not one"
            " this API issues. Read the stored contract again and supply the"
            " token from that read."
            if code == CONTRACT_EDIT_TOKEN_MALFORMED
            else (
                "The contract was not written: the stored contract changed since"
                " the edit token was read, or the request conflicts with the"
                " stored identity. Read the stored contract again and reconcile"
                " the draft before saving."
            )
        )
        return HTTPException(
            status_code=409,
            detail={
                "error": "conflict",
                "code": code,
                "message": message,
            },
        )
    return HTTPException(
        status_code=409,
        detail={
            "error": "conflict",
            "code": code or "contract_revision_capture_refused",
            "message": (
                "The contract was not written: its stored terms could not be captured"
                " as an immutable economic revision, so overwriting them could destroy"
                " evidence. Nothing was changed."
            ),
            "reason": detail,
        },
    )


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
