"""ETRM and ERP import contracts over HTTP: list them, and check a file (DATA-1).

``GET /api/imports/contracts`` lists the versioned file contracts
(``application/import_contracts``). ``POST /api/imports/{contract_id}/validate`` checks one
CSV file against its contract, row by row, and answers what storing it would do; it stores
nothing. Storing is the operator's ``scripts/ops/import_contract_file.py --commit``, so no
HTTP call writes the book of record's data, and nothing is booked, nominated or paid.

ETRM/ERP 导入契约：列出契约、校验文件（不写入）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.concurrency import run_in_threadpool

router = APIRouter(tags=["imports"])

#: Largest file the check takes over HTTP; larger extracts go through the operator script.
MAX_VALIDATE_BYTES = 8 * 1024 * 1024


def _meta(**extra) -> dict:
    return {"research_only": True, "human_review_required": True, **extra}


@router.get("/api/imports/contracts")
def list_import_contracts() -> dict:
    """The versioned ETRM and ERP file contracts: columns, key and where rows land."""

    from eurogas_nexus.application.import_contracts import contracts_catalogue

    return {"data": contracts_catalogue(), "meta": _meta(stores_nothing=True)}


@router.post(
    "/api/imports/{contract_id}/validate",
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"text/csv": {"schema": {"type": "string"}}},
            "description": "The file, UTF-8 CSV with a header row",
        }
    },
)
async def validate_import_file(
    contract_id: str,
    request: Request,
    system: str = Query(..., min_length=1, max_length=32,
                        description="Sending system, e.g. Endur, Allegro, SAP"),
    on_error: str = Query(default="reject_file", pattern="^(reject_file|skip_rows)$"),
) -> dict:
    """Check a CSV file against its contract; each refused row with its line and reason.

    Answers the rows, the accepted and refused ones, and, when the runtime store is
    configured, what storing would create, update, leave unchanged or remove. Nothing is
    stored, booked, nominated or sent.
    """

    body = await request.body()
    if len(body) > MAX_VALIDATE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "file_too_large",
                    "message": f"at most {MAX_VALIDATE_BYTES} bytes; use the operator script"},
        )
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(
            status_code=422, detail={"code": "encoding_invalid", "message": "send UTF-8"}
        ) from None
    # Parsing and the dry-run against the store block: the thread pool, not the event loop.
    report = await run_in_threadpool(_validate_import, contract_id, text, system, on_error)
    return {"data": report.as_dict(), "meta": _meta(stores_nothing=True)}


def _validate_import(contract_id: str, text: str, system: str, on_error: str):
    """Check the file against its contract (blocking: run in the thread pool)."""

    from eurogas_nexus.application.import_contracts import ImportContractError, run_import

    session_factory = _session_factory()
    try:
        if session_factory is None:
            return run_import(contract_id, text, system=system, on_error=on_error)
        with session_factory() as session:
            report = run_import(
                contract_id, text, system=system, on_error=on_error, session=session
            )
            session.rollback()
            return report
    except ImportContractError as exc:
        status = 404 if exc.code == "contract_unknown" else 422
        raise HTTPException(
            status_code=status, detail={"code": exc.code, "message": exc.message}
        ) from exc


def _session_factory():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return None
    return get_session_factory()
