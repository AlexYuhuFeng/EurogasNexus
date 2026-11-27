"""Versions: what a release bundle holds, putting one in place, and deciding how to go back.

A release bundle is the folder the developers send (or the helpdesk downloads)::

    release.json            {"version", "api_image", "api_image_archive"?, "web_archive", "sha256"}
    nexus, nexusctl/        this program
    deploy/compose.yaml     the stack for that version
    deploy/Caddyfile
    web.tar.gz              the web client (static files)
    images/api.tar          optional: the application image, for a PC without internet access

``scripts/release/package_small_desk_bundle.py`` builds one.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

from nexusctl.stack import Runner

#: Migration declarations a downgrade may cross (application/database_upgrade.DOWNGRADABLE).
DOWNGRADABLE = frozenset({"reversible", "conditional", "no-op"})


class ReleaseError(RuntimeError):
    """The bundle is incomplete or damaged; the message says what to do."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_release(bundle: Path) -> dict:
    """The bundle's release.json, after checking every file it names is there and intact."""

    path = bundle / "release.json"
    if not path.is_file():
        raise ReleaseError(
            f"{bundle} is not a release folder (release.json is missing). Unpack the release "
            "file you were sent and run the command from inside it."
        )
    release = json.loads(path.read_text(encoding="utf-8"))
    for key in ("version", "api_image", "web_archive"):
        if not release.get(key):
            raise ReleaseError(f"release.json has no {key}; ask the developers for a new bundle")
    for name in ("deploy/compose.yaml", "deploy/Caddyfile", release["web_archive"]):
        if not (bundle / name).is_file():
            raise ReleaseError(f"the release folder is missing {name}; unpack it again")
    for name, expected in (release.get("sha256") or {}).items():
        target = bundle / name
        if not target.is_file() or _sha256(target) != expected:
            raise ReleaseError(
                f"{name} in the release folder is damaged (its checksum differs); download or "
                "copy the release again"
            )
    return release


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as tar:
        members = []
        for member in tar.getmembers():
            target = (destination / member.name).resolve()
            if root != target and root not in target.parents:
                raise ReleaseError(f"{archive.name} holds a path outside its folder; refused")
            if member.issym() or member.islnk() or member.isdev():
                raise ReleaseError(f"{archive.name} holds a link or device; refused")
            members.append(member)
        try:
            tar.extractall(destination, members=members, filter="data")
        except TypeError:  # Python without extraction filters: the members were checked above
            tar.extractall(destination, members=members)


def install_release(bundle: Path, release: dict, releases_dir: Path, runner: Runner) -> Path:
    """Put a release in ``releases/<version>/`` and make its image available. Idempotent."""

    target = releases_dir / release["version"]
    staging = releases_dir / (release["version"] + ".staging")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    shutil.copyfile(bundle / "release.json", staging / "release.json")
    shutil.copyfile(bundle / "deploy" / "compose.yaml", staging / "compose.yaml")
    shutil.copyfile(bundle / "deploy" / "Caddyfile", staging / "Caddyfile")
    web_root = staging / "web"
    _safe_extract(bundle / release["web_archive"], web_root)
    # The archive may hold the files at its top or in one folder (dist/).
    if not (web_root / "index.html").is_file():
        children = [item for item in web_root.iterdir() if item.is_dir()]
        if len(children) == 1 and (children[0] / "index.html").is_file():
            inner = children[0]
            for item in inner.iterdir():
                shutil.move(str(item), str(web_root / item.name))
            inner.rmdir()
    if not (web_root / "index.html").is_file():
        raise ReleaseError("the web client in the release has no index.html; ask for a new bundle")
    if target.exists():
        shutil.rmtree(target)
    staging.rename(target)

    archive = release.get("api_image_archive")
    if archive and (bundle / archive).is_file():
        loaded = runner.run(["docker", "load", "--input", str(bundle / archive)], timeout=1800)
        if not loaded.ok:
            raise ReleaseError("Docker could not load the application image from the release")
    present = runner.run(["docker", "image", "inspect", release["api_image"]], timeout=60)
    if not present.ok:
        pulled = runner.run(["docker", "pull", release["api_image"]], timeout=1800)
        if not pulled.ok:
            raise ReleaseError(
                "the application image could not be downloaded. Check this PC can reach the "
                "internet, or ask the developers for a release with the image included "
                "(images/api.tar)."
            )
    return target


def load_installed(releases_dir: Path, version: str) -> tuple[Path, dict]:
    directory = releases_dir / version
    return directory, json.loads((directory / "release.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- going back
@dataclass(frozen=True)
class UndoPlan:
    """How `nexus undo-update` returns to the previous version.

    ``switch``: the update changed no database revision; start the previous version.
    ``downgrade``: every applied revision can be undone; downgrade, then start the previous one.
    ``restore``: a revision is declared irreversible (or declares nothing); restore the
    backup taken before the update into a fresh database, then start the previous version.
    """

    method: str
    reason: str
    blocking: tuple[str, ...] = ()


def plan_undo(applied: list[dict]) -> UndoPlan:
    """Decide from the revisions the update applied and their declarations. Pure."""

    if not applied:
        return UndoPlan("switch", "the update did not change the database")
    blocking = tuple(
        item["revision"] for item in applied if item.get("reversibility") not in DOWNGRADABLE
    )
    if blocking:
        return UndoPlan(
            "restore",
            "the update made database changes that cannot be undone ("
            + ", ".join(blocking)
            + "); going back means restoring the backup taken just before the update",
            blocking,
        )
    return UndoPlan(
        "downgrade", f"all {len(applied)} database change(s) of the update can be undone"
    )


def update_outcome(
    *, upgrade_returncode: int, ready: bool, failed_parts: list[str], probe: dict | None
) -> tuple[bool, str]:
    """Is the updated desk healthy? (healthy, the reason in words). Pure."""

    if upgrade_returncode != 0:
        return False, "the database upgrade did not complete"
    if failed_parts:
        return False, "these parts did not start: " + ", ".join(failed_parts)
    if not ready:
        return False, "the product did not become ready in time"
    database = (probe or {}).get("database") or {}
    if not database.get("reachable"):
        return False, "the application cannot read the database"
    if database.get("revision") != database.get("required_revision"):
        return False, "the database is not at the version this release needs"
    return True, "every part is running and the database is at the right version"
