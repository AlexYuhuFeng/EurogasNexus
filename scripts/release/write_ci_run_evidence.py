#!/usr/bin/env python
"""Write the same-SHA CI acceptance envelope from authoritative API metadata.

Read-only: the script asks the GitHub Actions API whether the exact release
commit has a completed, successful CI workflow run (the policy's
``ci_acceptance`` contract, including browser acceptance) whose required jobs
all succeeded, and records the answer as a schema-version 2 envelope for the
gate that declares ``verification: same_sha_ci_run``.

* ``PASS`` is written only from that API answer, with the verified run
  identity under ``report.ci_run`` for the release validator to re-check;
* missing, pending, failed, stale or unreachable state is recorded as ``FAIL``
  or ``PENDING_EXTERNAL`` and the gate stays blocked - never a fabricated
  PASS, and never a local shortcut;
* no GitHub write API (dispatch, release, tag, deployment) is ever called, and
  the credential is read from the environment and never written to output.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.release.ci_run_verification import (  # noqa: E402
    CI_VERIFICATION_KIND,
    CiRunVerdict,
    api_from_environment,
    load_ci_acceptance_spec,
    parse_repository,
    verified_run_report,
    verify_same_sha_ci_run,
)
from scripts.release.evidence_envelope import (  # noqa: E402
    DEFAULT_GATE_POLICY,
    build_envelope,
    load_gate_policy,
    write_envelope,
)


def _fail(message: str) -> int:
    print(f"write-ci-run-evidence: {message}", file=sys.stderr)
    return 2


def ci_verification_gate(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Return the single gate that requires same-SHA CI run verification."""

    gates = [
        gate
        for gate in policy.get("gates", [])
        if isinstance(gate, Mapping) and gate.get("verification") == CI_VERIFICATION_KIND
    ]
    if len(gates) != 1:
        raise ValueError(
            f"the gate policy must declare exactly one gate with "
            f"verification {CI_VERIFICATION_KIND!r}, found {len(gates)}"
        )
    return dict(gates[0])


def main(
    argv: list[str] | None = None,
    *,
    api_factory: Callable[[], tuple[object | None, str]] | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--job", required=True)
    parser.add_argument("--environment", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--output", required=True)
    parser.add_argument("--gate-policy", default=str(DEFAULT_GATE_POLICY))
    args = parser.parse_args(argv)

    policy = load_gate_policy(args.gate_policy)
    try:
        gate = ci_verification_gate(policy)
    except ValueError as error:
        return _fail(str(error))
    gate_id = str(gate.get("id", ""))
    if gate_id != "G1":
        return _fail(f"the same-SHA CI verification gate must be G1: {gate_id!r}")
    try:
        spec = load_ci_acceptance_spec(policy)
    except ValueError as error:
        return _fail(f"gate policy ci_acceptance section is invalid: {error}")
    if args.repo:
        try:
            requested_repo = parse_repository(args.repo)
        except ValueError as error:
            return _fail(str(error))
        if requested_repo != spec.repository:
            return _fail(
                f"repository {requested_repo} is not the gate policy trusted repository "
                f"{spec.repository}; same-SHA CI verification is restricted to it"
            )

    factory = api_factory or (lambda: api_from_environment(spec))
    api, unavailable = factory()
    verdict: CiRunVerdict | None = None
    report: dict[str, Any] | None = None
    if api is None:
        status = "PENDING_EXTERNAL"
        detail = unavailable or "the GitHub API transport is unavailable"
    else:
        verdict = verify_same_sha_ci_run(api, spec, head_sha=args.commit_sha)
        status = "PASS" if verdict.ok else "FAIL"
        detail = verdict.detail
        if verdict.ok:
            report = verified_run_report(verdict)

    try:
        envelope = build_envelope(
            gate_id=gate_id,
            status=status,
            detail=detail,
            commit_sha=args.commit_sha,
            subject={"kind": str(gate.get("subject_kind", "source")), "digests": {}},
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
            {
                "ok": True,
                "gate_id": gate_id,
                "status": status,
                "detail": detail,
                "verified_run_id": str(verdict.run["id"]) if verdict and verdict.run else "",
                "output": str(output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
