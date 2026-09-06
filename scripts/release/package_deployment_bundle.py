#!/usr/bin/env python
"""Package the Server operator deployment bundle (cross-platform).

Mirrors `package_deployment_bundle.sh` and is used by the local dry-run when a
native `zip` executable is unavailable. The bundle contains deployment
configuration and operator scripts only; it never embeds the desktop client or
the API image.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def package(output_dir: str | Path) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    staging_root = (
        Path(shutil.os.environ.get("TEMP", "/tmp"))
        / f"eurogas-nexus-deployment-{shutil.os.getpid()}"
    )
    server_root = staging_root / "Eurogas-Nexus-Server-Windows"
    if server_root.exists():
        shutil.rmtree(server_root)
    server_root.mkdir(parents=True)

    shutil.copytree(ROOT / "deploy" / "runtime", server_root / "deploy" / "runtime")
    windows_scripts = server_root / "scripts" / "install" / "windows"
    windows_scripts.mkdir(parents=True)
    shutil.copy2(
        ROOT / "scripts" / "install" / "windows" / "Deploy-EurogasNexus.ps1",
        windows_scripts / "Deploy-EurogasNexus.ps1",
    )
    shutil.copy2(
        ROOT / "scripts" / "install" / "windows" / "Install-EurogasNexusServerRuntime.ps1",
        windows_scripts / "Install-EurogasNexusServerRuntime.ps1",
    )
    shutil.copytree(ROOT / "docs" / "deployment", server_root / "docs" / "deployment")
    (server_root / "START-HERE.txt").write_text(
        "EUROGAS NEXUS SERVER FOR WINDOWS\n\n"
        "Advanced operator package for a dedicated Server deployment. Run the "
        "documented PowerShell preflight before installation. This package is "
        "not a desktop Client and does not embed the API image.\n",
        encoding="utf-8",
    )

    archive = target_dir / "Eurogas-Nexus-Server-Windows.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(server_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(staging_root))
    shutil.rmtree(staging_root, ignore_errors=True)
    return archive


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_dir", default="dist/releases")
    args = parser.parse_args(argv)
    archive = package(args.output_dir)
    print(archive)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
