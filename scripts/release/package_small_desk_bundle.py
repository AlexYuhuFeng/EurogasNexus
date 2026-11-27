"""Build the small-desk release folder that `nexus install` and `nexus update` read.

    python scripts/release/package_small_desk_bundle.py --version 1.0.0-beta.2 \\
        --api-image ghcr.io/<owner>/eurogasnexus-api@sha256:<digest> \\
        --web-dist clients/web/dist --out dist/ [--save-image]

``--save-image`` puts the application image in the folder (``images/api.tar``) for a PC that
cannot reach the image registry. Writes ``<out>/eurogas-nexus-small-desk-<version>/`` and
prints its path. The layout is documented in ``deploy/small-desk/nexusctl/release.py``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
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


def build(
    *, version: str, api_image: str, web_dist: Path, out: Path, image_archive: Path | None = None
) -> Path:
    if not (web_dist / "index.html").is_file():
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--api-image", required=True, help="image reference, pinned by digest")
    parser.add_argument("--web-dist", type=Path, default=ROOT / "clients/web/dist")
    parser.add_argument("--out", type=Path, default=ROOT / "dist")
    parser.add_argument("--save-image", action="store_true")
    args = parser.parse_args(argv)
    archive = None
    if args.save_image:
        args.out.mkdir(parents=True, exist_ok=True)
        archive = args.out / "api-image.tar"
        subprocess.run(
            ["docker", "save", "--output", str(archive), args.api_image], check=True
        )
    target = build(
        version=args.version,
        api_image=args.api_image,
        web_dist=args.web_dist,
        out=args.out,
        image_archive=archive,
    )
    if archive is not None:
        archive.unlink()
    print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
