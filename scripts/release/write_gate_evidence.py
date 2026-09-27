#!/usr/bin/env python
"""Write one schema-version 2 gate-evidence envelope (PILOT-B).

Writers never invent evidence identity: the commit SHA, workflow, job,
environment and run identity are supplied by the caller from its own execution
context. The subject kind and the NOT_APPLICABLE permission come from the gate
policy, and artifact/image digests are computed from the files being shipped -
so a writer cannot relabel a source test as an artifact test, bypass a gate
with NOT_APPLICABLE, or mark a PASS without binding the tested subject.

The envelope is re-verified against the release context, the actual bundle and
the gate policy by ``scripts/release/validate_stable_release.py``; this script
only refuses obviously contradictory or malformed writer input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.evidence_envelope import (  # noqa: E402
    API_IMAGE_DIGEST_KEY,
    DEFAULT_GATE_POLICY,
    SHA256_DIGEST,
    VALID_STATUSES,
    build_envelope,
    gate_entry,
    load_gate_policy,
    write_envelope,
)
from scripts.release.release_artifacts import sha256_file  # noqa: E402


def _fail(message: str) -> int:
    print(f"write-gate-evidence: {message}", file=sys.stderr)
    return 2


def _artifact_digest(artifacts_dir: Path, name: str) -> str:
    if name != Path(name).name or name in {"", ".", ".."}:
        raise ValueError(f"subject artifact must be a plain file name: {name!r}")
    path = artifacts_dir / name
    if not path.is_file():
        raise ValueError(f"subject artifact is not present: {path}")
    return f"sha256:{sha256_file(path)}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-id", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--detail", default="")
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--artifacts-dir")
    parser.add_argument(
        "--subject-artifact",
        action="append",
        default=[],
        metavar="NAME",
        help="tested artifact file name; repeatable (artifact-bound gates)",
    )
    parser.add_argument(
        "--image-digest",
        default="",
        help="published api image manifest digest (image-bound gates)",
    )
    parser.add_argument(
        "--report",
        help="optional JSON report to embed under 'report' for human detail",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--gate-policy", default=str(DEFAULT_GATE_POLICY))
    args = parser.parse_args(argv)

    status = args.status.upper()
    if status not in VALID_STATUSES:
        return _fail(f"status must be one of {sorted(VALID_STATUSES)}: {args.status!r}")

    policy = load_gate_policy(args.gate_policy)
    gate = gate_entry(policy, args.gate_id)
    if gate is None:
        return _fail(f"gate id {args.gate_id!r} is not declared in the gate policy")
    kind = gate.get("subject_kind")
    if kind not in {"source", "artifact", "image"}:
        return _fail(f"gate {args.gate_id!r} does not declare a valid subject_kind")
    if status == "NOT_APPLICABLE" and not gate.get("not_applicable_allowed", False):
        return _fail(
            f"NOT_APPLICABLE is not permitted for gate {args.gate_id!r}; "
            "a policy change is required"
        )
    if gate.get("verification") == "same_sha_ci_run":
        return _fail(
            f"gate {args.gate_id!r} requires authoritative same-SHA CI verification; "
            "write it with scripts/release/write_ci_run_evidence.py so the run identity "
            "comes from the GitHub API instead of a hand-written claim"
        )
    if kind == "source" and (args.subject_artifact or args.image_digest):
        return _fail(
            f"gate {args.gate_id!r} is source-bound and must not declare artifact "
            "digests; source tests are not artifact tests"
        )

    digests: dict[str, str] = {}
    try:
        if kind == "artifact":
            if args.image_digest:
                return _fail(f"gate {args.gate_id!r} is artifact-bound, not image-bound")
            if status == "PASS" and not args.subject_artifact:
                return _fail(
                    f"gate {args.gate_id!r} is artifact-bound; a PASS must bind at "
                    "least one tested artifact digest"
                )
            if args.subject_artifact and not args.artifacts_dir:
                return _fail("--subject-artifact requires --artifacts-dir")
            artifacts_dir = Path(args.artifacts_dir) if args.artifacts_dir else None
            for name in args.subject_artifact:
                digests[name] = _artifact_digest(artifacts_dir, name)
        elif kind == "image":
            if args.subject_artifact:
                return _fail(f"gate {args.gate_id!r} is image-bound, not artifact-bound")
            if args.image_digest:
                if SHA256_DIGEST.fullmatch(args.image_digest) is None:
                    return _fail(
                        "--image-digest must be sha256:<64 lowercase hex>: "
                        f"{args.image_digest!r}"
                    )
                digests[API_IMAGE_DIGEST_KEY] = args.image_digest
            elif status == "PASS":
                return _fail(
                    f"gate {args.gate_id!r} is image-bound; a PASS must bind the "
                    "tested image digest"
                )
    except ValueError as error:
        return _fail(str(error))

    report = None
    if args.report:
        try:
            report = json.loads(Path(args.report).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return _fail(f"report file is not readable JSON: {error}")

    try:
        envelope = build_envelope(
            gate_id=args.gate_id,
            status=status,
            detail=args.detail,
            commit_sha=args.commit_sha,
            subject={"kind": kind, "digests": digests},
            producer={
                "workflow": args.workflow,
                "job": args.job,
                "environment": args.environment,
                "run_id": args.run_id,
                "run_url": args.run_url,
            },
        )
    except ValueError as error:
        return _fail(str(error))
    if report is not None:
        envelope["report"] = report

    output = write_envelope(args.output, envelope)
    print(
        json.dumps(
            {"ok": True, "gate_id": args.gate_id, "status": status, "output": str(output)},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
