#!/usr/bin/env python
"""Gate-first, digest-preserving promotion of the tested API image (PILOT-C/D).

The release workflow builds the API image once and records its multi-platform
manifest digest. The build publishes only a run-attempt-unique candidate tag,
which is staging exposure and never approval. This module is the only writer of
the customer-facing channel tag, and the workflow runs it exclusively in the
gate-first promotion jobs, after

* the publish job created the GitHub Release for this exact commit,
* post-publication verification succeeded, and
* the same fail-closed ``validate_stable_release.py`` gate the publish job ran
  passed on the same ``release-final`` bundle - before the registry login and
  before any write in the same job.

Promotion changes status, not bytes: the channel tag is created by copying the
already-published tested multi-platform index (``docker buildx imagetools
create``); this module never builds and never pushes layers. Exact preservation
of the multi-platform index is *verified*, never assumed: after the copy the
tag is re-inspected and must resolve to exactly the tested digest with both
reviewed platforms, otherwise the run fails closed with escalation text.

Registry inspection uses documented CLI output only. ``docker buildx imagetools
inspect --raw`` prints the original, unformatted manifest JSON for the
reference (per the local CLI's ``--help``); this module reads those bytes,
hashes them to establish the digest the reference resolves to (content
addressing: a manifest digest *is* the SHA-256 of the served manifest bytes),
and parses the same bytes as JSON for the media type and platform descriptors.
A reformatted rendering of the manifest - for example the Go-marshalled
``--format '{{json .Manifest}}'`` output - is never hashed as a registry
digest, because a reconstruction is not the content-addressed original. The
digest-addressed subject (``image@<tested digest>``) is the calibration point:
the bytes it serves must hash to the tested digest, allowing for exactly one
trailing newline added by the CLI's output formatting; the interpretation that
matched is then applied to the tag, so both digests share one explicitly
verified basis.

Registry behaviour is treated conservatively. Only an explicit registry
manifest-missing marker (``MANIFEST_UNKNOWN`` / "manifest unknown" wording,
optionally "manifest not found") counts as absence; a generic "not found" -
which can also come from a missing binary, an unreadable config file or an
unclassified registry failure - refuses with no write. Authentication,
permission, network and contextual HTTP 5xx signals refuse even when a
manifest-missing marker also appears anywhere in the output; the whole
stdout/stderr is classified before any truncation for display. Every input,
including the timeout (which must be finite and positive), is validated before
a command runs; every command is an argv list without a shell and has a hard
timeout.

Overwrite policy, stated exactly: the registry credential this tool runs with
is not restricted from overwriting the tag - refusing an observed conflict is
this tool's policy, not a limitation of the credential. The check-then-write
pair is not atomic and an external writer can race it; keeping this workflow
the exclusive writer of the package is a documented operational prerequisite
that the lock itself cannot enforce. A post-copy inspection that fails to
confirm the tested digest does not prove that the tag exists: the tag state is
left UNKNOWN (it may resolve to the tested digest, to another digest, or not
exist), and the run stops for manual inspection instead of retrying or
repairing.

What this does not claim: the live behaviour of ``docker buildx imagetools
create`` against GHCR (index/digest preservation and tag visibility), the
exact bytes ``--raw`` prints for each manifest shape, and the registry's
explicit manifest-missing wording have not been verified against a registry by
this repository. This tool implements the fail-closed preparatory machinery
and refuses rather than assume those guarantees; a controlled registry
rehearsal remains open evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

# Only the reviewed GHCR repository shape is accepted. Uppercase, extra path
# segments, another registry or any shell metacharacter is refused before a
# command runs; executed commands are argv lists, so a validated input is
# never re-parsed by a shell.
REPOSITORY = re.compile(
    r"ghcr\.io/[a-z0-9](?:[a-z0-9-]*[a-z0-9])?/[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?"
)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TAG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,127}")

# Only a real multi-platform index may be promoted.
INDEX_MEDIA_TYPES = frozenset(
    {
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    }
)
# The index must contain the real platforms the build produces. ``arm64/v8``
# is the reviewed arm64 variant (an empty variant is the plain form);
# ``unknown/unknown`` descriptors are attestations, are allowed, and are
# neither required nor counted.
REQUIRED_PLATFORM_VARIANTS = {
    ("linux", "amd64"): frozenset({""}),
    ("linux", "arm64"): frozenset({"", "v8"}),
}
REQUIRED_PLATFORMS = frozenset(f"{os_name}/{arch}" for os_name, arch in REQUIRED_PLATFORM_VARIANTS)

# ``candidate-*`` is staging exposure that must never become the channel tag.
# ``sha-*`` alias naming is retired for this slice: a rebuild of the same
# source need not produce the same digest, so the alias would be ambiguous.
RETIRED_TAG_PREFIXES = ("candidate-", "sha-")
DEFAULT_TIMEOUT_SECONDS = 120.0
BYTE_RULES = ("exact", "trailing-newline")

# Absence requires an explicit registry manifest-missing marker: the
# ``MANIFEST_UNKNOWN`` registry error code or its "manifest unknown" wording
# (some registries word it "manifest not found"). A bare "not found" is never
# absence: a missing binary, an unreadable credential config or any
# unclassified failure can produce the same phrase.
ABSENCE_PATTERN = re.compile(
    r"manifest[\s._-]*unknown|manifest[\s._-]*not[\s._-]*found", re.IGNORECASE
)
# Refusal signals win over absence when both appear anywhere in the full
# output. HTTP server-error detection is contextual (status wording next to a
# 5xx code, or the standard reason phrase): a bare ``5ddd`` substring would
# also match hex digits inside digests and hashes.
REFUSAL_PATTERN = re.compile(
    r"unauthorized|authentication|forbidden|denied|credential|permission|"
    r"\btls\b|handshake|dial |dialing|connection|timeout|timed out|no such host|"
    r"i/o error|\beof\b|unexpected status|invalid reference|"
    r"\bhttp(?:/[0-9.]+)?\s+5\d\d\b|"
    r"\bstatus(?: code)?[\s:=]+5\d\d\b|"
    r"\bcode[\s:=]+5\d\d\b|"
    r"\b5\d\d\s+(?:internal server error|bad gateway|service unavailable|"
    r"gateway timeout|not implemented|loop detected|insufficient storage)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CommandResult:
    """One registry command's outcome; ``timed_out`` is a distinct failure.

    ``stdout_raw`` keeps the exact bytes the command wrote, which is the only
    correct input for hashing: text capture could normalise line endings.
    """

    argv: tuple[str, ...]
    returncode: int = -1
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    stdout_raw: bytes = b""


Runner = Callable[[Sequence[str], float], CommandResult]
RunCommand = Callable[[Sequence[str]], CommandResult]


def subprocess_runner(argv: Sequence[str], timeout: float) -> CommandResult:
    """Run one registry command as an argv list, never through a shell.

    The timeout is enforced by ``subprocess.run`` itself and surfaces as
    ``timed_out``: a hung or unreachable registry is a refusal, never an
    absence and never a stalled workflow. Output is captured as bytes so the
    manifest can be hashed exactly as served.
    """

    command = tuple(argv)
    try:
        completed = subprocess.run(command, capture_output=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CommandResult(command, timed_out=True)
    except OSError as error:
        return CommandResult(command, stderr=f"command could not be started: {error}")
    stdout_raw = completed.stdout or b""
    stderr_raw = completed.stderr or b""
    return CommandResult(
        command,
        returncode=completed.returncode,
        stdout=stdout_raw.decode("utf-8", "replace"),
        stderr=stderr_raw.decode("utf-8", "replace"),
        stdout_raw=stdout_raw,
    )


@dataclass(frozen=True)
class InspectOutcome:
    """The classified state of one registry reference."""

    state: str  # "present" | "absent" | "refused"
    digest: str = ""
    platforms: frozenset[str] = frozenset()
    satisfied_platforms: frozenset[str] = frozenset()
    byte_rule: str = ""  # "exact" | "trailing-newline" when present
    detail: str = ""


@dataclass(frozen=True)
class IndexParse:
    """The parsed structure of one index manifest; ``detail`` is the refusal."""

    platforms: frozenset[str] = frozenset()
    satisfied_platforms: frozenset[str] = frozenset()
    detail: str = ""


@dataclass(frozen=True)
class PromotionResult:
    """The promotion decision and the exact commands executed to reach it."""

    ok: bool
    outcome: str  # "noop" | "promoted" | "refused" | "verification_failed" | "invalid_input"
    detail: str
    image: str = ""
    tag: str = ""
    tested_digest: str = ""
    observed_digest: str = ""
    commands: tuple[tuple[str, ...], ...] = ()


def _bounded(text: str, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def parse_index_manifest(content: bytes) -> IndexParse:
    """Parse the original manifest bytes as a reviewed image index, or refuse.

    This parses the bytes ``--raw`` prints - the same documented JSON schema
    the ``--format '{{json .Manifest}}'`` rendering shows - without hashing
    any reformatted variant. The media type must be a real image index, every
    descriptor must carry a valid ``sha256:`` digest, and platform fields must
    be well-formed; ``unknown/unknown`` attestation descriptors are allowed
    and ignored. Anything absent or ambiguous is a refusal, never a guess.
    """

    try:
        document = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        return IndexParse(detail=f"the manifest bytes are not valid JSON ({error})")
    if not isinstance(document, dict):
        return IndexParse(detail="the manifest is not a JSON object")
    media_type = document.get("mediaType")
    if not isinstance(media_type, str) or media_type not in INDEX_MEDIA_TYPES:
        return IndexParse(
            detail=(
                f"the manifest mediaType {media_type!r} is not a reviewed image index "
                f"type {sorted(INDEX_MEDIA_TYPES)}; only a multi-platform index may "
                "be promoted"
            )
        )
    descriptors = document.get("manifests")
    if not isinstance(descriptors, list):
        return IndexParse(detail="the index has no manifest descriptor list")
    platforms: set[str] = set()
    satisfied: set[str] = set()
    for position, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            return IndexParse(detail=f"index descriptor {position} is not an object")
        descriptor_digest = descriptor.get("digest")
        if not isinstance(descriptor_digest, str) or DIGEST.fullmatch(descriptor_digest) is None:
            return IndexParse(
                detail=(
                    f"index descriptor {position} has no valid sha256 digest: "
                    f"{descriptor_digest!r}"
                )
            )
        descriptor_media_type = descriptor.get("mediaType")
        if not isinstance(descriptor_media_type, str) or not descriptor_media_type:
            return IndexParse(detail=f"index descriptor {position} has no mediaType")
        platform = descriptor.get("platform")
        if platform is None:
            # The OCI index allows descriptors without platform information.
            continue
        if not isinstance(platform, dict):
            return IndexParse(
                detail=f"index descriptor {position} has a malformed platform: {platform!r}"
            )
        os_name = platform.get("os")
        architecture = platform.get("architecture")
        if (
            not isinstance(os_name, str)
            or not os_name
            or not isinstance(architecture, str)
            or not architecture
        ):
            return IndexParse(
                detail=(
                    f"index descriptor {position} has an unparseable platform "
                    f"(os={os_name!r}, architecture={architecture!r})"
                )
            )
        variant = platform.get("variant", "")
        if not isinstance(variant, str):
            return IndexParse(
                detail=f"index descriptor {position} has a non-string platform variant"
            )
        if (os_name, architecture) == ("unknown", "unknown"):
            # Attestation descriptors (provenance/SBOM) use unknown/unknown.
            continue
        platforms.add(f"{os_name}/{architecture}" + (f"/{variant}" if variant else ""))
        for (required_os, required_arch), variants in REQUIRED_PLATFORM_VARIANTS.items():
            if (os_name, architecture) == (required_os, required_arch) and variant in variants:
                satisfied.add(f"{required_os}/{required_arch}")
    return IndexParse(platforms=frozenset(platforms), satisfied_platforms=frozenset(satisfied))


def inspect_reference(
    reference: str,
    run: RunCommand,
    *,
    expected_digest: str | None = None,
    byte_rule: str | None = None,
) -> InspectOutcome:
    """Inspect one registry reference and classify the outcome.

    The reference is read with ``docker buildx imagetools inspect --raw``,
    which prints the original, unformatted manifest JSON. The served bytes are
    hashed to establish the digest the reference resolves to and parsed as
    JSON for the index structure; a reformatted rendering is never hashed or
    trusted as a digest.

    ``expected_digest`` makes this call the calibration point (the tested
    ``image@digest`` reference): the served bytes must hash to it, allowing
    for exactly one trailing newline added by the CLI's output formatting, and
    the selected interpretation is reported in ``byte_rule``. Calls for the
    tag then pass that ``byte_rule`` so both digests share one verified basis.

    Only an explicit registry manifest-missing marker is classified as
    absence. Authentication, permission, network, contextual HTTP 5xx,
    timeout and every unclassified or ambiguous failure is refused, so a
    private or unreachable registry can never be read as "the tag does not
    exist" and then silently written.
    """

    result = run(["docker", "buildx", "imagetools", "inspect", "--raw", reference])
    if result.timed_out:
        return InspectOutcome(
            "refused",
            detail=(
                f"the registry command for {reference} timed out; the registry state "
                "is unknown and a timeout is never treated as absence"
            ),
        )
    if result.returncode != 0:
        # The whole output is classified; only the displayed excerpt is bounded.
        evidence = f"{result.stderr}\n{result.stdout}"
        if REFUSAL_PATTERN.search(evidence):
            return InspectOutcome(
                "refused",
                detail=(
                    f"the registry command for {reference} failed with an authentication, "
                    "permission, network or server error, which is never treated as "
                    f"absence: {_bounded(evidence)}"
                ),
            )
        if ABSENCE_PATTERN.search(evidence):
            return InspectOutcome(
                "absent",
                detail=(
                    f"the registry reports no manifest for {reference} (explicit "
                    f"manifest-missing marker): {_bounded(evidence)}"
                ),
            )
        return InspectOutcome(
            "refused",
            detail=(
                f"the registry command for {reference} failed without an explicit "
                "manifest-missing marker and without a recognised refusal signal; "
                f"refusing to guess: {_bounded(evidence) or 'no output'}"
            ),
        )
    raw = result.stdout_raw
    if not raw:
        return InspectOutcome(
            "refused",
            detail=(
                f"the registry command for {reference} reported success without "
                "manifest bytes; refusing to interpret that as a state"
            ),
        )
    candidates = [("exact", raw)]
    if raw.endswith(b"\n"):
        candidates.append(("trailing-newline", raw[:-1]))
    if expected_digest is not None:
        matches = [
            (rule, content) for rule, content in candidates if _sha256(content) == expected_digest
        ]
        if len(matches) != 1:
            return InspectOutcome(
                "refused",
                detail=(
                    f"the manifest bytes served for {reference} do not hash to the "
                    f"tested digest {expected_digest} (allowing for one CLI-appended "
                    "trailing newline); the served content is not the tested manifest"
                ),
            )
        rule, content = matches[0]
    else:
        if byte_rule not in BYTE_RULES:
            raise ValueError("byte_rule must be established by the tested-digest inspection")
        if byte_rule == "trailing-newline":
            if not raw.endswith(b"\n"):
                return InspectOutcome(
                    "refused",
                    detail=(
                        f"the registry command output for {reference} does not carry the "
                        "trailing newline observed for the tested digest; refusing to "
                        "reinterpret the bytes"
                    ),
                )
            content = raw[:-1]
        else:
            content = raw
        rule = byte_rule
    parsed = parse_index_manifest(content)
    if parsed.detail:
        return InspectOutcome(
            "refused",
            detail=f"the manifest for {reference} is ambiguous or unsupported: {parsed.detail}",
        )
    return InspectOutcome(
        "present",
        digest=_sha256(content),
        platforms=parsed.platforms,
        satisfied_platforms=parsed.satisfied_platforms,
        byte_rule=rule,
    )


def validate_image(image: object) -> str:
    """Validate the reviewed GHCR repository before any command can run."""

    if not isinstance(image, str) or REPOSITORY.fullmatch(image) is None:
        raise ValueError(
            "image must be the reviewed lowercase GHCR repository "
            f"ghcr.io/<owner>/eurogasnexus-api: {image!r}"
        )
    return image


def validate_digest(digest: object) -> str:
    """Validate the content-addressed digest before any command can run."""

    if not isinstance(digest, str) or DIGEST.fullmatch(digest) is None:
        raise ValueError(f"digest must be sha256:<64 lowercase hex>: {digest!r}")
    return digest


def validate_tag(tag: object) -> str:
    """Validate the channel tag; it is never derived, repaired or guessed."""

    if not isinstance(tag, str) or TAG.fullmatch(tag) is None:
        raise ValueError(f"tag must match {TAG.pattern}: {tag!r}")
    if tag == "latest":
        raise ValueError("refusing to promote the mutable 'latest' tag")
    for prefix in RETIRED_TAG_PREFIXES:
        if tag.startswith(prefix):
            raise ValueError(
                f"refusing to promote {tag!r}: '{prefix}*' tags are staging or retired "
                "naming, never the released channel tag"
            )
    return tag


def validate_timeout(timeout: object) -> float:
    """Validate the per-command timeout: finite and strictly positive."""

    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError(f"timeout must be a finite positive number of seconds: {timeout!r}")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError(f"timeout must be a finite positive number of seconds: {timeout!r}")
    return float(timeout)


def promote_image(
    *,
    image: str,
    tag: str,
    digest: str,
    runner: Runner | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> PromotionResult:
    """Promote the tested digest to ``tag``, or refuse without writing.

    Every input - image, tag, digest and timeout - is validated here, before
    any command can run, so direct library callers get the same fail-closed
    contract as the CLI. The registry work then only follows the verified
    path: verify the tested digest and its platforms, inspect the target tag,
    classify, copy an absent tag, then re-inspect and require the exact tested
    digest with the reviewed platforms. Every path is fail-closed, and no path
    deletes anything.
    """

    try:
        image = validate_image(image)
        tag = validate_tag(tag)
        digest = validate_digest(digest)
        timeout = validate_timeout(timeout)
    except ValueError as error:
        return PromotionResult(
            ok=False,
            outcome="invalid_input",
            detail=_bounded(f"invalid promotion input: {error}"),
        )

    execute = runner or subprocess_runner
    commands: list[tuple[str, ...]] = []

    def run(argv: Sequence[str]) -> CommandResult:
        command = tuple(argv)
        commands.append(command)
        return execute(command, timeout)

    def result(outcome: str, detail: str, observed: str = "") -> PromotionResult:
        return PromotionResult(
            ok=outcome in {"noop", "promoted"},
            outcome=outcome,
            detail=detail,
            image=image,
            tag=tag,
            tested_digest=digest,
            observed_digest=observed,
            commands=tuple(commands),
        )

    subject = inspect_reference(f"{image}@{digest}", run, expected_digest=digest)
    if subject.state != "present":
        return result(
            "refused",
            "refusing to promote: the tested multi-platform digest "
            f"{image}@{digest} is not verifiably present in the registry "
            f"({subject.detail})",
        )
    missing = sorted(REQUIRED_PLATFORMS - subject.satisfied_platforms)
    if missing:
        return result(
            "refused",
            f"refusing to promote: the tested digest does not report real {missing}; only "
            "the reviewed multi-platform index may be promoted",
        )

    reference = f"{image}:{tag}"
    current = inspect_reference(reference, run, byte_rule=subject.byte_rule)
    if current.state == "refused":
        return result("refused", f"refusing to write {reference}: {current.detail}")
    if current.state == "present":
        if current.digest != digest:
            return result(
                "refused",
                f"refusing to overwrite {reference}: it currently resolves to "
                f"{current.digest}, not the tested digest {digest}. Refusing the "
                "observed conflict is this run's policy - the registry credential "
                "itself is not restricted from overwriting - and an external writer "
                "racing this check cannot be excluded. An owner/incident decision is "
                "required.",
                current.digest,
            )
        missing = sorted(REQUIRED_PLATFORMS - current.satisfied_platforms)
        if missing:
            return result(
                "refused",
                f"refusing to accept {reference}: it resolves to the tested digest but "
                f"does not report real {missing}",
                current.digest,
            )
        return result(
            "noop",
            f"{reference} already resolves to the tested digest {digest}; nothing to do "
            "(idempotent retry)",
            current.digest,
        )

    created = run(
        ["docker", "buildx", "imagetools", "create", "--tag", reference, f"{image}@{digest}"]
    )
    if created.timed_out:
        return result(
            "refused",
            f"the manifest copy for {reference} timed out; the tag state is UNKNOWN (the "
            "write may or may not have taken effect). Inspect the tag manually before "
            "re-running; this tool retries nothing and writes nothing further.",
        )
    if created.returncode != 0:
        return result(
            "refused",
            f"the manifest copy for {reference} failed and no successful write is "
            "claimed; if the failure was an interrupted connection the tag state is "
            f"UNKNOWN, so inspect the tag before re-running: "
            f"{_bounded(created.stderr or created.stdout or 'no output')}",
        )

    after = inspect_reference(reference, run, expected_digest=digest)
    if after.state != "present" or REQUIRED_PLATFORMS - after.satisfied_platforms:
        return result(
            "verification_failed",
            f"FAIL: the manifest copy for {reference} reported success, but the post-copy "
            f"inspection did not confirm it as the tested digest {digest} with "
            f"{sorted(REQUIRED_PLATFORMS)} "
            f"({after.detail or after.digest or 'no manifest'}). The tag state is UNKNOWN: "
            "it may resolve to the tested digest, to another digest, or not exist at all "
            "- a failed verification is not proof that the tag exists. Stop, do not "
            "re-run blindly, and escalate to the owner/incident process with this result.",
            after.digest,
        )
    return result(
        "promoted",
        f"{reference} now resolves to the tested multi-platform digest {digest} "
        f"({sorted(REQUIRED_PLATFORMS)})",
        after.digest,
    )


def load_metadata(path: Path) -> tuple[str, str]:
    """Read and validate the run's ``image-metadata.json`` (image, digest)."""

    if not path.is_file():
        raise ValueError(f"image metadata is missing: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"image metadata is unreadable: {error}") from error
    if not isinstance(data, dict):
        raise ValueError("image metadata must be a JSON object with image and digest")
    image = validate_image(data.get("image"))
    digest = validate_digest(data.get("digest"))
    return image, digest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Promote the tested API image digest to a channel tag"
    )
    parser.add_argument(
        "--metadata",
        required=True,
        help="path to the run's image-metadata.json (image and tested digest)",
    )
    parser.add_argument(
        "--tag", required=True, help="channel tag to create, e.g. 0.5.0-preview or 0.5.0"
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="hard timeout for each registry command (finite and positive)",
    )
    parser.add_argument("--result-output", help="path for the machine-readable promotion result")
    args = parser.parse_args(argv)

    def report(payload: dict) -> int:
        text = json.dumps(payload, indent=2, sort_keys=True)
        if args.result_output:
            target = Path(args.result_output)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text + "\n", encoding="utf-8")
        print(text)
        return 0 if payload.get("ok") else 1

    try:
        timeout = validate_timeout(args.timeout_seconds)
        image, digest = load_metadata(Path(args.metadata))
        tag = validate_tag(args.tag)
    except ValueError as error:
        return report({"ok": False, "outcome": "invalid_input", "detail": _bounded(str(error))})

    result = promote_image(image=image, tag=tag, digest=digest, timeout=timeout)
    return report(
        {
            "schema_version": 1,
            "ok": result.ok,
            "outcome": result.outcome,
            "detail": result.detail,
            "image": result.image,
            "tag": result.tag,
            "tested_digest": result.tested_digest,
            "observed_digest": result.observed_digest,
            "platforms": sorted(REQUIRED_PLATFORMS),
            "commands": [" ".join(command) for command in result.commands],
        }
    )


if __name__ == "__main__":
    raise SystemExit(main())
