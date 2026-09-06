"""Deterministic release-version and tag semantics.

Canonical policy:

* Application version: ``X.Y.Z`` (semantic version core), kept in
  ``pyproject.toml`` and mirrored by ``eurogas_nexus.version``.
* STABLE tag: ``vX.Y.Z``.
* RC tag: ``vX.Y.Z-rc.N`` (N >= 1).
* PREVIEW tag: ``vX.Y.Z-preview.N.<shortsha>`` (N >= 1, 7-40 lowercase hex).

Legacy tags such as ``v0.5-preview-107-df3bde9`` are historical and are never
accepted for new releases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class ReleaseChannel(StrEnum):
    """Canonical release channels."""

    PREVIEW = "preview"
    RC = "rc"
    STABLE = "stable"


_SEMVER_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_TAG_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True, order=True)
class SemVer:
    """A minimal semantic-version core (``major.minor.patch``)."""

    major: int
    minor: int
    patch: int

    @property
    def core(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    def __str__(self) -> str:
        return self.core


@dataclass(frozen=True)
class ReleaseTag:
    """A parsed canonical release tag."""

    app_version: SemVer
    channel: ReleaseChannel
    prerelease_number: int | None
    git_sha: str | None

    @property
    def tag(self) -> str:
        return build_release_tag(
            self.app_version,
            self.channel,
            self.prerelease_number,
            self.git_sha,
        )


def parse_app_version(value: str) -> SemVer:
    """Parse the canonical application version core.

    Release metadata is expressed separately (channel, prerelease number,
    commit), so the application version itself never carries a channel suffix.
    """

    normalized = value.strip().removeprefix("v")
    match = _SEMVER_CORE_RE.match(normalized)
    if match is None:
        raise ValueError(
            f"Invalid application version {value!r}; expected X.Y.Z without a channel suffix."
        )
    return SemVer(int(match.group(1)), int(match.group(2)), int(match.group(3)))


def build_release_tag(
    version: SemVer | str,
    channel: ReleaseChannel | str,
    prerelease_number: int | None = None,
    git_sha: str | None = None,
) -> str:
    """Build a canonical release tag from separated release metadata."""

    resolved = parse_app_version(version) if isinstance(version, str) else version
    resolved_channel = ReleaseChannel(channel)
    if resolved_channel is ReleaseChannel.STABLE:
        return f"v{resolved.core}"
    if prerelease_number is None or prerelease_number < 1:
        raise ValueError(f"{resolved_channel.value} release requires prerelease_number >= 1.")
    if resolved_channel is ReleaseChannel.RC:
        return f"v{resolved.core}-rc.{prerelease_number}"
    if git_sha is None or not _TAG_SHA_RE.match(git_sha):
        raise ValueError("preview release requires a 7-40 character lowercase hexadecimal git SHA.")
    return f"v{resolved.core}-preview.{prerelease_number}.{git_sha}"


def parse_release_tag(tag: str) -> ReleaseTag:
    """Parse a canonical release tag, rejecting legacy/arbitrary tags."""

    normalized = tag.strip()
    if not normalized.startswith("v"):
        raise ValueError(f"Release tag must start with 'v': {normalized!r}")

    core = normalized[1:]
    stable_match = _SEMVER_CORE_RE.match(core)
    if stable_match is not None:
        return ReleaseTag(
            app_version=SemVer(
                int(stable_match.group(1)),
                int(stable_match.group(2)),
                int(stable_match.group(3)),
            ),
            channel=ReleaseChannel.STABLE,
            prerelease_number=None,
            git_sha=None,
        )

    rc_suffix = "-rc."
    if rc_suffix in core:
        version_text, remainder = core.split(rc_suffix, 1)
        version_match = _SEMVER_CORE_RE.match(version_text)
        rc_match = re.match(r"^(0|[1-9]\d*)$", remainder)
        if version_match is not None and rc_match is not None:
            number = int(rc_match.group(1))
            if number >= 1:
                return ReleaseTag(
                    app_version=SemVer(
                        int(version_match.group(1)),
                        int(version_match.group(2)),
                        int(version_match.group(3)),
                    ),
                    channel=ReleaseChannel.RC,
                    prerelease_number=number,
                    git_sha=None,
                )

    preview_suffix = "-preview."
    if preview_suffix in core:
        version_text, remainder = core.split(preview_suffix, 1)
        version_match = _SEMVER_CORE_RE.match(version_text)
        preview_match = re.match(r"^(0|[1-9]\d*)\.([0-9a-f]+)$", remainder)
        if version_match is not None and preview_match is not None:
            number = int(preview_match.group(1))
            git_sha = preview_match.group(2)
            if number >= 1 and _TAG_SHA_RE.match(git_sha):
                return ReleaseTag(
                    app_version=SemVer(
                        int(version_match.group(1)),
                        int(version_match.group(2)),
                        int(version_match.group(3)),
                    ),
                    channel=ReleaseChannel.PREVIEW,
                    prerelease_number=number,
                    git_sha=git_sha,
                )

    raise ValueError(
        f"Invalid release tag {normalized!r}; expected vX.Y.Z, vX.Y.Z-rc.N, "
        "or vX.Y.Z-preview.N.<shortsha>."
    )
