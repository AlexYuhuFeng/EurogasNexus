"""Versioned, typed gate-evidence envelopes (schema version 2).

One envelope describes exactly one gate's evidence for exactly one release
identity:

* ``schema_version``/``gate_id``/``status``/``detail`` - what the file claims;
* ``commit_sha`` - the full tested commit, verified against the release context;
* ``subject`` - what was tested: the source commit (``kind: source``) or precise
  artifact/image digests (``kind: artifact``/``kind: image``), verified against
  the actual files and trusted metadata in the release bundle - never against
  values declared in the same evidence file;
* ``producer`` - the workflow/job/run that produced the evidence, checked
  against the authorised producer profiles in the gate policy;
* ``produced_at_utc`` - when it was produced, checked against the freshness
  window in the gate policy.

Trust boundary: every field is self-declared JSON text. Envelope validation
removes status-only, old-format, foreign, stale, future-dated, malformed and
unapproved-producer evidence, and binds evidence to identity that the release
run re-derives from the release context and the actual bundle. It is not
cryptographic provenance: a hostile actor who can write into the evidence
directory can still claim an authorised producer identity. Signed attestation
and GitHub-run metadata verification remain documented residual work.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GATE_POLICY = ROOT / "scripts" / "release" / "policy" / "stable_gate_policy.json"

EVIDENCE_SCHEMA_VERSION = 2
VALID_STATUSES = frozenset({"PASS", "FAIL", "PENDING_EXTERNAL", "NOT_APPLICABLE"})
SUBJECT_KINDS = frozenset({"source", "artifact", "image"})
API_IMAGE_DIGEST_KEY = "api_image_digest"

FULL_SHA = re.compile(r"[0-9a-f]{40}")
SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_utc_timestamp(value: object) -> datetime | None:
    """Return a UTC timezone-aware datetime, or None for anything else.

    RFC 3339-style ``Z`` suffixes are accepted; naive timestamps and non-zero
    UTC offsets are refused because evidence freshness is compared in UTC.
    """

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    return parsed.astimezone(UTC)


def load_gate_policy(path: str | Path = DEFAULT_GATE_POLICY) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gate_entry(policy: dict, gate_id: str) -> dict | None:
    for gate in policy.get("gates", []):
        if gate.get("id") == gate_id:
            return gate
    return None


def build_envelope(
    *,
    gate_id: str,
    status: str,
    commit_sha: str,
    subject: dict,
    producer: dict,
    detail: str = "",
    approval: dict | None = None,
    produced_at_utc: str | None = None,
) -> dict:
    """Build one schema-version 2 envelope, refusing malformed writer input.

    Validation here is a writer-side guard, not the release check: the gate
    validator re-verifies every field against the release context, the actual
    artifacts and the gate policy.
    """

    resolved_status = str(status).upper()
    if resolved_status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}: {status!r}")
    if not isinstance(commit_sha, str) or FULL_SHA.fullmatch(commit_sha) is None:
        raise ValueError(
            "commit_sha must be the full 40-character lowercase commit SHA of the "
            f"tested source: {commit_sha!r}"
        )
    if not isinstance(subject, dict):
        raise ValueError("subject must be a mapping with kind and digests")
    kind = subject.get("kind")
    if kind not in SUBJECT_KINDS:
        raise ValueError(f"subject kind must be one of {sorted(SUBJECT_KINDS)}: {kind!r}")
    digests = subject.get("digests") or {}
    if not isinstance(digests, dict):
        raise ValueError("subject digests must be a mapping of name to sha256 digest")
    for name, digest in digests.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f"subject digest name must be a non-empty string: {name!r}")
        if not isinstance(digest, str) or SHA256_DIGEST.fullmatch(digest) is None:
            raise ValueError(
                f"subject digest for {name!r} must be sha256:<64 lowercase hex>: {digest!r}"
            )
    if kind == "source" and digests:
        raise ValueError(
            "a source-bound subject must not carry artifact digests; source tests "
            "bind the commit SHA and must not be relabelled with artifact hashes"
        )
    if not isinstance(producer, dict):
        raise ValueError("producer must be a mapping with workflow, job and environment")
    for field in ("workflow", "job", "environment"):
        value = producer.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"producer {field} must be a non-empty string")
    for field in ("run_id", "run_url"):
        value = producer.get(field, "")
        if not isinstance(value, str):
            raise ValueError(f"producer {field} must be a string when present")
    if approval is not None and not isinstance(approval, dict):
        raise ValueError("approval must be a mapping when present")
    timestamp = produced_at_utc or utc_now_iso()
    if parse_utc_timestamp(timestamp) is None:
        raise ValueError(f"produced_at_utc must be a UTC timestamp: {timestamp!r}")

    envelope: dict = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "gate_id": gate_id,
        "status": resolved_status,
        "detail": str(detail),
        "commit_sha": commit_sha,
        "subject": {"kind": kind, "digests": dict(digests)},
        "producer": {
            "workflow": producer["workflow"],
            "job": producer["job"],
            "environment": producer["environment"],
            "run_id": producer.get("run_id", ""),
            "run_url": producer.get("run_url", ""),
        },
        "produced_at_utc": timestamp,
    }
    if approval is not None:
        envelope["approval"] = dict(approval)
    return envelope


def write_envelope(path: str | Path, envelope: dict) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
