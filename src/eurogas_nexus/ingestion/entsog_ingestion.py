"""ENTSOG page archival and canonical persistence inside caller-owned transactions.

Raw pages are retained even when normalization, revision safety or a partial
reference query refuses canonical writes. Archive failure rolls back archival
as a group and cannot create canonical rows with imaginary lineage. No helper
commits, grants authority or performs HTTP reads.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.models import FlowObservationRecord
from eurogas_nexus.db.repositories.entsog_observation_persistence import (
    upsert_entsog_observation_rows,
)
from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload
from eurogas_nexus.ingestion.entsog_transport import EntsogFetchResult, EntsogPage
from eurogas_nexus.ingestion.public_sources import (
    entsog_capacity_observations_from_json,
    entsog_flow_observations_from_json,
    entsog_market_hubs_from_connectionpoints,
    entsog_reference_facilities_from_connectionpoints,
    entsog_reference_nodes_from_connectionpoints,
    entsog_tso_access_points_from_json,
)


class EntsogIngestionError(RuntimeError):
    code = "entsog_ingestion_error"


class EntsogArchiveLineageError(EntsogIngestionError):
    code = "entsog_archive_lineage_required"


class EntsogEmptyNormalizationError(EntsogIngestionError):
    code = "entsog_empty_normalization"


class EntsogPartialReferenceError(EntsogIngestionError):
    code = "entsog_partial_reference_refused"


def archive_entsog_pages(
    session: Any,
    results: Sequence[EntsogFetchResult],
) -> list[list[tuple[EntsogPage, str]]]:
    """Archive every query/page with its exact bytes, actual receipt and count."""
    if not results or any(not result.pages for result in results):
        raise EntsogArchiveLineageError("ENTSOG fetch results and raw pages are required.")
    archived: list[list[tuple[EntsogPage, str]]] = []
    try:
        with session.begin_nested():
            for result in results:
                query_pages = []
                for page in result.pages:
                    archive_id = f"raw-{uuid4().hex[:20]}"
                    record = archive_raw_payload(
                        session, archive_id=archive_id, **page.raw_archive_values()
                    )
                    if (
                        record is None
                        or record.archive_id != archive_id
                        or record.payload_sha256 != page.payload_sha256
                    ):
                        raise EntsogArchiveLineageError(
                            "ENTSOG exact raw archive identity was not confirmed."
                        )
                    query_pages.append((page, archive_id))
                archived.append(query_pages)
    except SQLAlchemyError:
        raise EntsogArchiveLineageError(
            "ENTSOG raw archival failed; canonical rows were not written."
        ) from None
    return archived


def _stamp_page_rows(
    rows: list[dict[str, Any]],
    page: EntsogPage,
    archive_id: str,
    result: EntsogFetchResult,
    run_id: str,
) -> list[dict[str, Any]]:
    for row in rows:
        metadata = dict(row.get("metadata_json") or {})
        metadata.update(page.lineage_metadata(archive_id=archive_id))
        metadata.update(
            {
                "raw_archive_id": archive_id,
                "ingestion_run_id": run_id,
                "adapter_version": "entsog-bounded-ingestor/1",
                "fetch_reference": result.source_reference,
                "fetch_complete": result.complete,
                "snapshot_consistent": False,
            }
        )
        row["metadata_json"] = metadata
        row["source_reference"] = page.source_reference
    return rows


def persist_entsog_observations(
    session: Any,
    *,
    results: Sequence[EntsogFetchResult],
    model: Any,
    run_id: str,
) -> dict[str, int]:
    """Archive all queries first, then atomically append-or-verify observations.

    Each query must produce usable canonical rows. NA/invalid records can be
    skipped within a query, but the counts disclose that reduction. A zero-row
    query refuses the whole canonical batch, including mixed capacity products.
    """
    archived = archive_entsog_pages(session, results)
    normalizer = (
        entsog_flow_observations_from_json
        if model is FlowObservationRecord
        else entsog_capacity_observations_from_json
    )
    rows = []
    for result, pages in zip(results, archived, strict=True):
        query_rows = []
        for page, archive_id in pages:
            normalized = normalizer(page.payload, observed_at_utc=page.received_at_utc)
            query_rows.extend(_stamp_page_rows(normalized, page, archive_id, result, run_id))
        if not query_rows:
            raise EntsogEmptyNormalizationError("ENTSOG query produced no canonical observations.")
        rows.extend(query_rows)
    outcome = upsert_entsog_observation_rows(session, model, rows)
    received = sum(result.record_count for result in results)
    return {
        "records": len(rows),
        "received_records": received,
        "skipped_records": received - len(rows),
        "archived_pages": sum(map(len, archived)),
        **outcome,
    }


def persist_entsog_reference(
    session: Any,
    *,
    results: Sequence[EntsogFetchResult],
    run_id: str,
    replace_network: Callable[..., dict[str, Any]],
) -> dict[str, Any]:
    """A partial query can be archived but must never replace/delete topology.

    Exhaustion is traversal completeness only; no snapshot guarantee is invented.
    The existing scoped replacement callback remains authoritative for nonempty
    tables and node/access-point handling, inside a canonical savepoint.
    """
    archived = archive_entsog_pages(session, results)
    if (
        len(results) != 2
        or results[0].dataset != "connectionpoints"
        or results[1].dataset != "operatorpointdirections"
    ):
        raise EntsogIngestionError("ENTSOG reference queries must include both reference datasets.")
    if any(not result.complete for result in results):
        raise EntsogPartialReferenceError(
            "ENTSOG partial reference queries kept existing topology."
        )
    families: dict[str, list[dict[str, Any]]] = {
        "nodes": [],
        "facilities": [],
        "hubs": [],
        "tso_access_points": [],
    }
    for result, pages in zip(results, archived, strict=True):
        query_normalized = 0
        normalizers = (
            (
                ("nodes", entsog_reference_nodes_from_connectionpoints),
                ("facilities", entsog_reference_facilities_from_connectionpoints),
                ("hubs", entsog_market_hubs_from_connectionpoints),
            )
            if (result.dataset == "connectionpoints")
            else (("tso_access_points", entsog_tso_access_points_from_json),)
        )
        for page, archive_id in pages:
            for name, normalizer in normalizers:
                rows = normalizer(page.payload)
                families[name].extend(_stamp_page_rows(rows, page, archive_id, result, run_id))
                query_normalized += len(rows)
        if not query_normalized:
            raise EntsogEmptyNormalizationError(
                "ENTSOG reference query produced no canonical rows."
            )
    with session.begin_nested():
        summary = replace_network(session, **families)
    return {
        "records": sum(map(len, families.values())),
        "received_records": sum(result.record_count for result in results),
        "archived_pages": sum(map(len, archived)),
        "skipped_tables": summary["skipped_tables"],
        "replaced": summary["replaced"],
    }
