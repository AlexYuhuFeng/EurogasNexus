"""DB-first /api/contracts routes for capacity and route context."""

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["contracts"])


@router.get("/api/contracts/capacity")
def list_capacity_contracts(request: Request) -> dict:
    """List capacity profile contracts from the runtime DB.

    返回容量档案契约列表（按生效时间倒序）；DB 未配置或不可用时
    降级为空数据并告警，绝不返回编造的容量。

    Args:
        request: Incoming FastAPI request (envelope context).

    Returns:
        Enveloped capacity rows with ``runtime-postgresql`` source tag,
        or an empty enveloped response with a warning.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the DB is
            configured but the read fails.
    """

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is required for capacity profile context."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import CapacityProfileRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = (
                session.query(CapacityProfileRecord)
                .order_by(CapacityProfileRecord.valid_from_utc.desc())
                .all()
            )
            data = [
                {
                    "contract_id": row.contract_id,
                    "route_name": row.point_name,
                    "from_node_id": row.point_name,
                    "to_node_id": row.point_name,
                    "capacity_boe_d": row.capacity_mwh_per_day,
                    "unit": "MWh/d",
                    "start_utc": row.valid_from_utc.isoformat(),
                    "end_utc": row.valid_to_utc.isoformat(),
                    "status": row.firmness,
                    "source_reference": row.source_reference,
                }
                for row in rows
            ]
            warnings = [] if data else ["No capacity profiles are stored in the runtime DB."]
            return _env(data, request, source="runtime-postgresql", warnings=warnings)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/contracts/routes")
def list_route_eligibility(request: Request) -> dict:
    """List route eligibility context (no generated routes are returned).

    返回路线资格上下文：路由发现必须由源拓扑/TSO 准入/容量/费率推导，
    本端点不生成路线，未配置 DB 时降级为空并告警。

    Args:
        request: Incoming FastAPI request (envelope context).

    Returns:
        Enveloped empty list with a derivation warning.
    """

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is required for route eligibility context."],
        )

    return _env(
        [],
        request,
        source="runtime-postgresql",
        warnings=[
            "Route discovery must be derived from source topology, TSO access, "
            "capacity profiles, and tariff rows; no generated routes are returned."
        ],
    )


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
            "message": "Runtime database is configured but unavailable for contract reads.",
            "error_class": exc.__class__.__name__,
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
            "warnings": warnings or [],
        },
    }


@router.get("/api/contracts/delivery-performance")
def get_delivery_performance(
    request: Request,
    days: int = Query(90, ge=7, le=730),
    contract_id: str | None = Query(None, max_length=128),
    format: str = Query("json", pattern="^(json|csv|xlsx|pdf)$"),
):
    """Bilateral supply delivered against nominations and DCQ, per contract.

    双边供应合同的实际交付：分配量对比提名量与日合同量，偏差、波动与摇摆使用。

    One summary row per stored upstream contract with delivery records in the window:
    deviation from nominations (short and long days beyond the nomination tolerance, the
    imbalance volume), delivery volatility and the 7-day trend against DCQ, and days outside
    the contract's swing. With ``contract_id`` the response adds that contract's daily
    series. Contracts follow portfolio isolation.
    """

    from datetime import UTC, datetime, timedelta

    from eurogas_nexus.api.routes.public.portfolio import _hub_from_text
    from eurogas_nexus.domain.risk.delivery import (
        DeliveryDay,
        DeliveryTerms,
        daily_series,
        delivery_performance,
    )

    if not _db_is_configured():
        return _env(
            {"rows": []},
            request,
            source="runtime-db-not-configured",
            warnings=["RUNTIME_DB_NOT_CONFIGURED"],
        )
    since = datetime.now(UTC).date() - timedelta(days=days)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import (
            ContractDeliveryRecord,
            UpstreamResourceContractRecord,
        )
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.security.portfolio_scope import restrict

        with get_session_factory()() as session:
            query = restrict(
                session.query(UpstreamResourceContractRecord),
                UpstreamResourceContractRecord,
                session,
            )
            if contract_id:
                query = query.filter(UpstreamResourceContractRecord.contract_id == contract_id)
            contracts = {row.contract_id: row for row in query.all()}
            records = (
                session.query(ContractDeliveryRecord)
                .filter(ContractDeliveryRecord.contract_id.in_(list(contracts) or [""]))
                .filter(ContractDeliveryRecord.gas_day >= since)
                .all()
                if contracts
                else []
            )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    by_contract: dict[str, list] = {}
    tso: dict[str, str] = {}
    for record in records:
        by_contract.setdefault(record.contract_id, []).append(
            DeliveryDay(record.gas_day, record.nominated_mwh, record.allocated_mwh)
        )
        if record.tso:
            tso[record.contract_id] = record.tso
    rows, series = [], []
    for key in sorted(by_contract):
        contract = contracts[key]
        terms = DeliveryTerms(
            contract_id=key,
            contract_name=contract.contract_name,
            hub=_hub_from_text(contract.delivery_point_name),
            dcq_mwh=float(contract.delivery_quantity_mwh_per_day),
            nomination_tolerance_pct=float(contract.nomination_tolerance_pct or 0.0),
            delivery_tolerance_pct=float(contract.delivery_tolerance_pct or 0.0),
            tso=tso.get(key, ""),
        )
        rows.append(delivery_performance(terms, by_contract[key]))
        if contract_id:
            series = daily_series(terms, by_contract[key])
    warnings = (
        []
        if rows
        else [
            "No nominations or allocations are loaded for this window; load them with "
            "scripts/ops/import_contract_deliveries.py."
        ]
    )
    if format != "json":
        from eurogas_nexus.api.csv_export import report_response

        return report_response(
            series if contract_id else rows,
            report=f"delivery-{contract_id}" if contract_id else "delivery-performance",
            format=format,
            title=f"Deliveries {contract_id}" if contract_id else "Delivery performance",
            about=[("Window", f"last {days} gas days")],
        )
    return _env(
        {"rows": rows, "series": series, "days": days},
        request,
        source="runtime-postgresql",
        warnings=warnings,
    )


@router.post("/api/contracts/intake")
async def post_contract_intake(
    request: Request,
    file_name: str = Query("contract.pdf", max_length=200),
) -> dict:
    """Read a contract or confirmation PDF into a draft for review (nothing is stored).

    合同 PDF 导入：提取文本（扫描件在服务器装有 Tesseract 时做 OCR），识别合同条款并给出
    页码与原文证据；只返回草稿，由人工核对后经受治理的合同写入保存。

    The body is the PDF itself (``Content-Type: application/pdf``). The response holds the
    draft ``record`` the contract workbench loads, every recognised term with its page and
    the words it came from, and warnings for scans, conversions and terms not found. The
    upload is audited by its SHA-256 only; the document is not kept.
    """

    import hashlib

    from eurogas_nexus.application.contract_intake import (
        MAX_PDF_BYTES,
        IntakeError,
        intake_pdf,
    )

    declared = int(request.headers.get("content-length") or 0)
    if declared > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail={"code": "pdf_too_large"})
    content = await request.body()
    try:
        result = intake_pdf(content, file_name=file_name)
    except IntakeError as exc:
        raise HTTPException(
            status_code=422, detail={"code": "pdf_unreadable", "message": str(exc)}
        ) from exc
    digest = hashlib.sha256(content).hexdigest()
    if _db_is_configured():
        try:
            from eurogas_nexus.db.repositories.audit import record_audit_event
            from eurogas_nexus.db.session import get_session_factory

            actor = getattr(getattr(request.state, "identity", None), "principal_id", None)
            with get_session_factory()() as session:
                record_audit_event(
                    session,
                    event_type="contract.intake",
                    principal=actor or "api",
                    action="contract.intake.read",
                    resource=f"pdf:{digest[:16]}",
                    outcome="extracted",
                    severity="info",
                    detail=f"sha256={digest} pages={result.pages} terms={len(result.terms)}",
                )
                session.commit()
        except _sqlalchemy_error_type() as exc:
            raise _db_unavailable(exc) from exc
    payload = result.as_dict()
    payload["sha256"] = digest
    return _env(payload, request, source="contract-intake", warnings=result.warnings)
