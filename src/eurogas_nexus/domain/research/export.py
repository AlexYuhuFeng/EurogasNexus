"""Dataset artifact export adapters (Parquet primary, CSV debug)."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from eurogas_nexus.domain.research.datasets import DatasetBuildResult


def export_parquet(
    result: DatasetBuildResult,
    output_path: str | Path,
    *,
    enforce_entitlement: bool = True,
) -> Path:
    """Export the dataset to Parquet.

    Export is entitlement-aware by contract; callers must have already checked
    the snapshot envelope. This function preserves nulls and timestamp data
    with PyArrow.
    """

    if enforce_entitlement:
        policies = {
            str(row.get("export_policy") or row.get("quality_state") or "").upper()
            for row in result.rows
        }
        if policies and not policies <= {"EXPORT_ALLOWED", "OBSERVED", "MISSING", "FORWARD_FILLED"}:
            raise PermissionError("EXPORT_DENIED_ENTITLEMENT")
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet export requires pyarrow; install the `research` extra."
        ) from exc

    arrays: dict[str, list[Any]] = {column: [] for column in result.columns}
    for row in result.rows:
        for column in result.columns:
            arrays[column].append(row.get(column))
    table = pa.table(arrays)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, target)
    return target


def export_csv(
    result: DatasetBuildResult,
    output_path: str | Path,
    *,
    enforce_entitlement: bool = True,
) -> Path:
    """Export the dataset to CSV for debugging/interoperability."""

    if enforce_entitlement:
        policies = {
            str(row.get("export_policy") or row.get("quality_state") or "").upper()
            for row in result.rows
        }
        if policies and not policies <= {"EXPORT_ALLOWED", "OBSERVED", "MISSING", "FORWARD_FILLED"}:
            raise PermissionError("EXPORT_DENIED_ENTITLEMENT")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=result.columns)
    writer.writeheader()
    for row in result.rows:
        writer.writerow({column: row.get(column) for column in result.columns})
    target.write_text(buffer.getvalue(), encoding="utf-8")
    return target
