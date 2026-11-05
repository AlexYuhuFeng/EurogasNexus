"""Shared numerical bundle identity for existing and task-oriented calculations."""

import sys
from functools import lru_cache
from importlib import metadata, resources

from eurogas_nexus.domain.analysis_contracts import analysis_manifest, content_hash


@lru_cache(maxsize=1)
def numerical_bundle_fingerprint():
    root = resources.files("eurogas_nexus")
    hashes = {}

    def visit(directory, prefix):
        for item in sorted(directory.iterdir(), key=lambda item: item.name):
            if item.is_dir() and item.name != "__pycache__":
                visit(item, f"{prefix}/{item.name}")
            elif item.name.endswith(".py"):
                import hashlib

                hashes[f"{prefix}/{item.name}"] = hashlib.sha256(item.read_bytes()).hexdigest()

    for package in ("domain", "application", "optimization"):
        visit(root.joinpath(package), package)
    return content_hash(
        {
            "files": hashes,
            "python": list(sys.version_info[:3]),
            "pydantic": metadata.version("pydantic"),
            "tzdata": metadata.version("tzdata"),
        }
    )


def calculation_manifest(kind, engine_version, inputs, *, versions=None, scopes=()):
    result = analysis_manifest(kind, engine_version, inputs, versions=versions, scopes=scopes)
    result["numerical_bundle_fingerprint"] = numerical_bundle_fingerprint()
    result["version_ref_basis"] = "DECLARED_UNLESS_RESOLVED_FROM_SERVER_RECORDS"
    result["manifest_hash"] = content_hash(
        {k: v for k, v in result.items() if k != "manifest_hash"}
    )
    return result
