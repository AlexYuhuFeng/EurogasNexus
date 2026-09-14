"""Dataset artifact materialization for CR-14 research builds.

CR14-ARTIFACT-001 storage decision (see
``core.config.ResearchArtifactConfig``): every materialized dataset snapshot
writes format-specific artifacts beneath one operator-configurable root,
``EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT``, defaulting to the git-ignored
``data/snapshots/`` directory of the checkout. Rationale: DATA_POLICY allows
local files for generated reports and snapshots, PostgreSQL remains the source
of truth for ingested runtime data, the directory can never be committed, and
the persisted ``dataset_snapshots.artifact_ref`` stays a short relative
reference instead of an absolute server path.

Rights boundary: artifacts are server-side storage of a governed research
snapshot. Writing them is not an export; the export route and the
``dataset.export`` capability derive the export policy server-side from
canonical provenance and refuse to serve a reference unless policy permits it.
Row export policy is therefore enforced at the serving boundary, and a build
never fails merely because a source is export-restricted.

Every write fails closed: an unusable root, an escaping path, or a failed
adapter raises ``ArtifactStoreUnavailable`` instead of returning a half-built
artifact list, so a build can never persist a snapshot that claims an artifact
which does not exist.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from eurogas_nexus.core.config import resolve_research_artifact_root
from eurogas_nexus.domain.research.datasets import DatasetBuildResult
from eurogas_nexus.domain.research.export import export_csv, export_parquet

# Deterministic precedence: Parquet is the analytical format, CSV the debug and
# interoperability format. The first registered artifact becomes the snapshot's
# ``artifact_ref``.
ARTIFACT_FORMAT_PRECEDENCE = ("parquet", "csv")
ARTIFACT_EXTENSIONS = {"parquet": "parquet", "csv": "csv"}
MAX_ARTIFACT_PATH_LENGTH = 512
MAX_SEGMENT_LENGTH = 96
_SAFE_SEGMENT = re.compile(r"[^A-Za-z0-9._-]+")


class ArtifactStoreUnavailable(RuntimeError):
    """Raised when the configured artifact root cannot hold a build artifact."""

    code = "artifact_store_unavailable"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def parquet_adapter_available() -> bool:
    """Return whether the optional Parquet adapter (pyarrow) is importable.

    PyArrow belongs to the optional ``research`` extra. It is never required for
    a build: without it a snapshot simply registers its CSV artifact only, and a
    Parquet export request fails closed as an unregistered format.
    """

    try:
        import pyarrow  # noqa: F401
    except ImportError:
        return False
    return True


def artifact_formats() -> tuple[str, ...]:
    """Return the artifact formats this deployment can materialize."""

    return tuple(
        artifact_format
        for artifact_format in ARTIFACT_FORMAT_PRECEDENCE
        if artifact_format != "parquet" or parquet_adapter_available()
    )


def safe_path_segment(value: str) -> str:
    """Return a filesystem-safe single path segment for a client-supplied id."""

    segment = _SAFE_SEGMENT.sub("_", str(value)).strip("._-")
    return (segment or "artifact")[:MAX_SEGMENT_LENGTH]


def artifact_id_for(dataset_snapshot_id: str, artifact_format: str) -> str:
    """Return the deterministic artifact identity for one snapshot/format."""

    digest = hashlib.sha256(f"{dataset_snapshot_id}|{artifact_format}".encode()).hexdigest()[
        :32
    ]
    return f"artifact:{artifact_format}:{digest}"


def _artifact_directory(dataset_snapshot_id: str) -> tuple[Path, Path]:
    root = resolve_research_artifact_root()
    try:
        resolved_root = root.resolve()
    except OSError as exc:
        raise ArtifactStoreUnavailable(
            f"artifact root cannot be resolved: {root}"
        ) from exc
    if resolved_root.exists() and not resolved_root.is_dir():
        raise ArtifactStoreUnavailable(
            f"artifact root is not a directory: {resolved_root}"
        )
    directory = root / safe_path_segment(dataset_snapshot_id)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        resolved_directory = directory.resolve()
    except OSError as exc:
        raise ArtifactStoreUnavailable(
            f"artifact root is not writable: {resolved_root}"
        ) from exc
    if not resolved_directory.is_relative_to(resolved_root):
        raise ArtifactStoreUnavailable(
            "artifact path escaped the configured research artifact root"
        )
    if not resolved_directory.is_dir():
        raise ArtifactStoreUnavailable(
            f"artifact directory is not usable: {resolved_directory}"
        )
    return resolved_root, resolved_directory


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_dataset_artifacts(result: DatasetBuildResult) -> list[dict[str, str]]:
    """Write the snapshot artifacts this deployment can produce.

    Returns persistable ``dataset_artifacts`` rows (``artifact_id``, ``format``,
    ``artifact_path``, ``sha256``) in ``ARTIFACT_FORMAT_PRECEDENCE`` order, where
    ``artifact_path`` is relative to the configured artifact root. The caller
    persists them together with the snapshot, so a snapshot never references an
    artifact that was not written.
    """

    root, directory = _artifact_directory(result.dataset_snapshot_id)
    artifacts: list[dict[str, str]] = []
    for artifact_format in artifact_formats():
        extension = ARTIFACT_EXTENSIONS[artifact_format]
        target = directory / f"dataset.{extension}"
        writer = export_parquet if artifact_format == "parquet" else export_csv
        try:
            # ``enforce_entitlement`` stays False: the row-level export policy is
            # enforced when a reference is served (export route /
            # ``dataset.export`` capability), never by internal storage.
            writer(result, target, enforce_entitlement=False)
            digest = _sha256_of(target)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ArtifactStoreUnavailable(
                f"artifact write failed for format {artifact_format!r}"
            ) from exc
        artifact_path = f"{safe_path_segment(result.dataset_snapshot_id)}/dataset.{extension}"
        if len(artifact_path) > MAX_ARTIFACT_PATH_LENGTH:
            raise ArtifactStoreUnavailable("artifact path exceeds the stored column limit")
        artifacts.append(
            {
                "artifact_id": artifact_id_for(result.dataset_snapshot_id, artifact_format),
                "format": artifact_format,
                "artifact_path": artifact_path,
                "sha256": digest,
            }
        )
    if not artifacts:
        raise ArtifactStoreUnavailable("no artifact format adapter is available")
    # Confirm containment once more after writing, so a symlinked directory can
    # never place a written file outside the configured root.
    for artifact in artifacts:
        written = (root / artifact["artifact_path"]).resolve()
        if not written.is_relative_to(root):
            raise ArtifactStoreUnavailable(
                "artifact file escaped the configured research artifact root"
            )
    return artifacts


def resolve_artifact_file(artifact_path: str) -> Path:
    """Return the absolute path of a stored artifact reference."""

    root = resolve_research_artifact_root()
    candidate = (root / str(artifact_path)).resolve()
    if not candidate.is_relative_to(root.resolve()):
        raise ArtifactStoreUnavailable("artifact reference escaped the artifact root")
    return candidate
