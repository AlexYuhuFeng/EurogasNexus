"""Deterministic release-version and tag semantics.

Canonical policy:

* Application version: ``X.Y.Z`` (semantic version core), optionally a beta
  pre-release of it. ``pyproject.toml`` holds the PEP 440 spelling
  (``1.0.0b1``); every other machine surface (runtime module, npm, Cargo,
  Tauri) holds the SemVer spelling (``1.0.0-beta.1``); people read the display
  spelling (``1.0.0-beta``). :class:`SemVer` derives every spelling, so one
  parser keeps them consistent (``scripts/release/check_version_consistency.py``).
* STABLE tag: ``vX.Y.Z``.
* BETA tag: ``vX.Y.Z-beta.N`` (N >= 1); ``vX.Y.Z-beta`` is accepted as the
  alias of ``-beta.1`` and keeps its spelling, because the GitHub Release is
  created on the tag that was pushed.
* RC tag: ``vX.Y.Z-rc.N`` (N >= 1).
* PREVIEW tag: ``vX.Y.Z-preview.N.<shortsha>`` (N >= 1, 7-40 lowercase hex).

Legacy tags such as ``v0.5-preview-107-df3bde9`` are historical and are never
accepted for new releases.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from functools import total_ordering


class ReleaseChannel(StrEnum):
    """Canonical release channels."""

    PREVIEW = "preview"
    BETA = "beta"
    RC = "rc"
    STABLE = "stable"


_SEMVER_CORE_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
# The application version: a core, optionally a beta in PEP 440 (1.0.0b1) or SemVer
# (1.0.0-beta.1) spelling. No other pre-release kind is a product version.
_APP_VERSION_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:b([1-9]\d*)|-beta\.([1-9]\d*))?$"
)
_TAG_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")


@total_ordering
@dataclass(frozen=True)
class SemVer:
    """A semantic-version core (``major.minor.patch``), optionally a beta of it.

    ``beta`` is the beta number (``1.0.0b1`` -> 1) or ``None`` for a final version;
    a beta sorts before its final version, as in SemVer and PEP 440.
    """

    major: int
    minor: int
    patch: int
    beta: int | None = None

    @property
    def core(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

    @property
    def is_prerelease(self) -> bool:
        return self.beta is not None

    @property
    def pep440(self) -> str:
        """``pyproject.toml`` spelling: ``1.0.0`` or ``1.0.0b1``."""

        return self.core if self.beta is None else f"{self.core}b{self.beta}"

    @property
    def semver(self) -> str:
        """Runtime, npm, Cargo and Tauri spelling: ``1.0.0`` or ``1.0.0-beta.1``."""

        return self.core if self.beta is None else f"{self.core}-beta.{self.beta}"

    @property
    def display(self) -> str:
        """What people read (About box, /api/health, documents): ``1.0.0-beta``."""

        return self.core if self.beta is None else f"{self.core}-beta"

    @property
    def debian(self) -> str:
        """Debian package version: ``1.0.0~beta1`` sorts before ``1.0.0`` in dpkg."""

        return self.core if self.beta is None else f"{self.core}~beta{self.beta}"

    def _key(self) -> tuple[int, int, int, int, int]:
        final = self.beta is None
        return (self.major, self.minor, self.patch, int(final), self.beta or 0)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self._key() < other._key()

    def __str__(self) -> str:
        return self.semver


@dataclass(frozen=True)
class ReleaseTag:
    """A parsed canonical release tag."""

    app_version: SemVer
    channel: ReleaseChannel
    prerelease_number: int | None
    git_sha: str | None
    #: ``vX.Y.Z-beta`` was pushed (the alias of ``-beta.1``); ``tag`` keeps that spelling.
    beta_alias: bool = False

    @property
    def tag(self) -> str:
        if self.beta_alias:
            return f"v{self.app_version.core}-beta"
        return build_release_tag(
            self.app_version,
            self.channel,
            self.prerelease_number,
            self.git_sha,
        )


def parse_app_version(value: str) -> SemVer:
    """Parse the application version: ``X.Y.Z``, ``X.Y.ZbN`` or ``X.Y.Z-beta.N``.

    Channel, prerelease number and commit of a *release* are expressed separately
    (:func:`parse_release_tag`); the only pre-release the application version itself
    carries is a beta, because a beta is a product version shown to customers.
    """

    normalized = value.strip().removeprefix("v")
    match = _APP_VERSION_RE.match(normalized)
    if match is None:
        raise ValueError(
            f"Invalid application version {value!r}; expected X.Y.Z, X.Y.ZbN or X.Y.Z-beta.N."
        )
    beta = match.group(4) or match.group(5)
    return SemVer(
        int(match.group(1)),
        int(match.group(2)),
        int(match.group(3)),
        int(beta) if beta else None,
    )


def display_version(value: str) -> str:
    """The display spelling of a version string (``1.0.0-beta.1`` -> ``1.0.0-beta``).

    A value that is not an application version (an operator override) is returned as is.
    """

    try:
        return parse_app_version(value).display
    except ValueError:
        return value.strip()


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
    if resolved_channel is ReleaseChannel.BETA:
        return f"v{resolved.core}-beta.{prerelease_number}"
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

    beta_suffix = "-beta"
    if beta_suffix in core:
        version_text, remainder = core.split(beta_suffix, 1)
        version_match = _SEMVER_CORE_RE.match(version_text)
        beta_match = re.match(r"^(?:\.([1-9]\d*))?$", remainder)
        if version_match is not None and beta_match is not None:
            number = int(beta_match.group(1)) if beta_match.group(1) else 1
            return ReleaseTag(
                app_version=SemVer(
                    int(version_match.group(1)),
                    int(version_match.group(2)),
                    int(version_match.group(3)),
                    number,
                ),
                channel=ReleaseChannel.BETA,
                prerelease_number=number,
                git_sha=None,
                beta_alias=beta_match.group(1) is None,
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
        f"Invalid release tag {normalized!r}; expected vX.Y.Z, vX.Y.Z-beta.N, "
        "vX.Y.Z-rc.N or vX.Y.Z-preview.N.<shortsha>."
    )
