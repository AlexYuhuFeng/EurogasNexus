#!/usr/bin/env python
"""Give a built desktop .deb the Debian spelling of a beta version.

Tauri writes the configured SemVer version (``1.0.0-beta.1``) into the package's
``control`` file. dpkg reads the last hyphen as the Debian revision and sorts
``1.0.0-beta.1`` *after* ``1.0.0``, so ``apt`` would call the later stable release a
downgrade. The Debian spelling ``1.0.0~beta1`` sorts before ``1.0.0``.

    python scripts/release/set_deb_version.py path/to/package.deb

The version comes from ``pyproject.toml`` through the one version helper
(``eurogas_nexus.release.versioning``). A final version (``1.0.0``) leaves the file
untouched. Needs ``dpkg-deb`` (present on the Ubuntu runners).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from scripts.release.release_metadata import canonical_version_identity  # noqa: E402

_VERSION_LINE = re.compile(r"^Version:\s*(?P<value>\S+)\s*$", re.MULTILINE)


def rewrite(deb: Path, version: str) -> str | None:
    """Set the control ``Version`` of ``deb`` to ``version``; return the old one if changed."""

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "pkg"
        subprocess.run(["dpkg-deb", "-R", str(deb), str(tree)], check=True)
        control = tree / "DEBIAN" / "control"
        text = control.read_text(encoding="utf-8")
        match = _VERSION_LINE.search(text)
        if match is None:
            raise SystemExit(f"{deb}: control file has no Version field")
        old = match.group("value")
        if old == version:
            return None
        control.write_text(
            _VERSION_LINE.sub(f"Version: {version}", text, count=1), encoding="utf-8"
        )
        rebuilt = Path(tmp) / deb.name
        subprocess.run(
            ["dpkg-deb", "--root-owner-group", "-b", str(tree), str(rebuilt)],
            check=True,
            stdout=subprocess.DEVNULL,
        )
        deb.write_bytes(rebuilt.read_bytes())
        return old


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("debs", nargs="+", type=Path)
    args = parser.parse_args(argv)

    identity = canonical_version_identity()
    if not identity.is_prerelease:
        print(f"{identity.pep440} is a final version; .deb files left as built")
        return 0
    for deb in args.debs:
        old = rewrite(deb, identity.debian)
        state = f"{old} -> {identity.debian}" if old else f"already {identity.debian}"
        print(f"{deb.name}: Version {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
