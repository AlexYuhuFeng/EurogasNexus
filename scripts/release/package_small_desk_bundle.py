"""Build the small-desk release folder that `nexus install` and `nexus update` read.

    python scripts/release/package_small_desk_bundle.py --version 1.0.0-beta.2 \\
        --api-image ghcr.io/<owner>/eurogasnexus-api@sha256:<digest> \\
        --web-dist clients/web/dist --out dist/ [--save-image]

The release workflow names the release instead of the version and image, and publishes one
archive (``eurogas-nexus-small-desk-<version>.tar.gz``, one top folder)::

    python scripts/release/package_small_desk_bundle.py \\
        --release-context release-context.json --image-digest sha256:<digest> \\
        --web-archive eurogas-nexus-web-<version>.tar.gz --out release-assets --archive

The image is the context's ``api_image`` pinned by the published digest, the same identity
the Server operator bundle carries (``package_deployment_bundle.py``). ``--save-image`` puts
the application image in the folder (``images/api.tar``) for a PC that cannot reach the
registry. Prints the folder (or archive) path. The layout is documented in
``deploy/small-desk/nexusctl/release.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SMALL_DESK = ROOT / "deploy" / "small-desk"
DOCS = (
    "docs/operations/SMALL_DESK_HELPDESK_CARD.md",
    "docs/operations/SMALL_DESK_INSTALL.md",
    "docs/operations/SMALL_DESK_INSTALL-CN.md",
    "docs/operations/SMALL_DESK_FALLBACK_CARD.md",
    "docs/operations/SMALL_DESK_FALLBACK_CARD-CN.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


IMAGE_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_REPOSITORY = re.compile(r"[a-z0-9][a-z0-9._/:-]*")


def archive_name(version: str) -> str:
    return f"eurogas-nexus-small-desk-{version}.tar.gz"


def from_release_context(context_path: Path, image_digest: str) -> tuple[str, str]:
    """(version, image reference) from the release context and the published digest."""

    context = json.loads(context_path.read_text(encoding="utf-8"))
    version = str(context["release_version"]).lstrip("v")
    repository = str(context.get("api_image") or "")
    if not IMAGE_REPOSITORY.fullmatch(repository) or "@" in repository:
        raise SystemExit(f"release context api_image {repository!r} is not an image repository")
    if not IMAGE_DIGEST.fullmatch(image_digest or ""):
        raise SystemExit("--image-digest must be an immutable sha256:<64 lowercase hex> digest")
    return version, f"{repository}@{image_digest}"


def _web_has_index(archive: Path) -> bool:
    with tarfile.open(archive, "r:gz") as tar:
        return any(name.lstrip("./") == "index.html" for name in tar.getnames())


def build(
    *,
    version: str,
    api_image: str,
    out: Path,
    web_dist: Path | None = None,
    web_archive: Path | None = None,
    image_archive: Path | None = None,
) -> Path:
    if web_archive is not None:
        if not web_archive.is_file() or not _web_has_index(web_archive):
            raise SystemExit(f"{web_archive} is not a web client archive with index.html")
    elif web_dist is None or not (web_dist / "index.html").is_file():
        raise SystemExit(f"{web_dist} has no index.html: build the web client first")
    target = out / f"eurogas-nexus-small-desk-{version}"
    if target.exists():
        shutil.rmtree(target)
    (target / "deploy").mkdir(parents=True)
    shutil.copy2(SMALL_DESK / "nexus", target / "nexus")
    shutil.copytree(
        SMALL_DESK / "nexusctl",
        target / "nexusctl",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for name in ("compose.yaml", "Caddyfile"):
        shutil.copy2(SMALL_DESK / name, target / "deploy" / name)
    shutil.copy2(ROOT / "deploy/runtime/database_roles.sql", target / "deploy/database_roles.sql")
    (target / "docs").mkdir()
    for doc in DOCS:
        if (ROOT / doc).is_file():
            shutil.copy2(ROOT / doc, target / "docs" / Path(doc).name)
    if web_archive is not None:
        shutil.copyfile(web_archive, target / "web.tar.gz")
    else:
        with tarfile.open(target / "web.tar.gz", "w:gz") as archive:
            for path in sorted(web_dist.rglob("*")):
                if path.is_file():
                    archive.add(path, arcname=str(path.relative_to(web_dist)))
    files = ["web.tar.gz", "deploy/compose.yaml", "deploy/Caddyfile", "deploy/database_roles.sql"]
    release = {"version": version, "api_image": api_image, "web_archive": "web.tar.gz"}
    if image_archive is not None:
        (target / "images").mkdir()
        shutil.copy2(image_archive, target / "images" / "api.tar")
        release["api_image_archive"] = "images/api.tar"
        files.append("images/api.tar")
    release["sha256"] = {name: sha256(target / name) for name in files}
    (target / "release.json").write_text(json.dumps(release, indent=2) + "\n", encoding="utf-8")
    (target / "nexus").chmod(0o755)
    return target


def make_archive(folder: Path) -> Path:
    """One .tar.gz with the folder at its top (the exec bit of `nexus` kept); the folder goes."""

    version = folder.name.removeprefix("eurogas-nexus-small-desk-")
    archive = folder.parent / archive_name(version)
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(folder, arcname=folder.name)
    shutil.rmtree(folder)
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--version")
    parser.add_argument("--api-image", help="image reference, pinned by digest")
    parser.add_argument("--release-context", type=Path,
                        help="release-context.json: the version and image repository")
    parser.add_argument("--image-digest", help="with --release-context: the published digest")
    parser.add_argument("--web-dist", type=Path, default=ROOT / "clients/web/dist")
    parser.add_argument("--web-archive", type=Path, help="the release's web client .tar.gz")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--save-image", action="store_true")
    parser.add_argument("--archive", action="store_true",
                        help="write eurogas-nexus-small-desk-<version>.tar.gz instead of a folder")
    args = parser.parse_args(argv)
    if args.release_context is not None:
        version, api_image = from_release_context(args.release_context, args.image_digest or "")
    elif args.version and args.api_image:
        version, api_image = args.version, args.api_image
    else:
        parser.error("give --release-context with --image-digest, or --version with --api-image")
    image = None
    if args.save_image:
        args.out.mkdir(parents=True, exist_ok=True)
        image = args.out / "api-image.tar"
        subprocess.run(["docker", "save", "--output", str(image), api_image], check=True)
    target = build(
        version=version,
        api_image=api_image,
        out=args.out,
        web_dist=None if args.web_archive else args.web_dist,
        web_archive=args.web_archive,
        image_archive=image,
    )
    if image is not None:
        image.unlink()
    print(make_archive(target) if args.archive else target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
