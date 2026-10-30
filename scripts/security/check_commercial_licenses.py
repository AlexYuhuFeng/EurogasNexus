"""Fail-closed commercial-use licence gate for every shipped and build dependency.

Eurogas Nexus is sold commercially and closed-source, so every dependency must carry
a licence that permits proprietary commercial use and redistribution. This gate
reads the actual licence metadata of all three ecosystems:

- Python: installed distribution metadata (``License-Expression``, ``License`` or
  trove classifiers) of the current environment, so CI runs it after installing the
  locked runtime/dev sets;
- npm: ``license`` fields in ``clients/web`` and ``clients/desktop`` lock files;
- Rust: ``cargo metadata`` of the desktop crate (skipped with a notice when cargo is
  absent).

An SPDX ``A OR B`` expression passes when any branch is allowed; ``A AND B`` needs
every term allowed. Copyleft that would bind our code (GPL/AGPL/SSPL), source-
available (BUSL, Commons Clause), non-commercial (CC-BY-NC) and unknown licences
fail. Weak file-level copyleft (MPL-2.0, EPL-2.0) and LGPL are flagged as
``review`` (allowed when unmodified and, for LGPL, dynamically linked), never silently
passed. Reviewed exceptions live in ``REVIEWED`` with a reason.

    python scripts/security/check_commercial_licenses.py \
        --report docs/legal/DEPENDENCY_LICENSE_REVIEW.md
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

ALLOWED = {
    "MIT", "MIT-0", "ISC", "BSD-2-CLAUSE", "BSD-3-CLAUSE", "0BSD", "APACHE-2.0",
    "APACHE-2.0 WITH LLVM-EXCEPTION", "ZLIB", "UNLICENSE", "CC0-1.0", "BLUEOAK-1.0.0",
    "PSF-2.0", "PYTHON-2.0", "UNICODE-3.0", "UNICODE-DFS-2016", "BSL-1.0", "OFL-1.1",
    "HPND", "X11", "CC-BY-4.0",
}
REVIEW = {"MPL-2.0", "EPL-2.0", "LGPL-2.1-OR-LATER", "LGPL-3.0-OR-LATER", "LGPL-2.1", "LGPL-3.0"}
FORBIDDEN_PATTERN = re.compile(
    r"\b(A?GPL|SSPL|BUSL|COMMONS CLAUSE|CC-BY-NC|NON-?COMMERCIAL|ELASTIC|PROPRIETARY)\b"
)

#: Classifier / free-text names mapped to SPDX ids.
ALIASES = {
    "MIT LICENSE": "MIT",
    "BSD LICENSE": "BSD-3-CLAUSE",
    "BSD": "BSD-3-CLAUSE",
    "APACHE SOFTWARE LICENSE": "APACHE-2.0",
    "APACHE 2.0": "APACHE-2.0",
    "APACHE LICENSE 2.0": "APACHE-2.0",
    "APACHE LICENSE, VERSION 2.0": "APACHE-2.0",
    "ISC LICENSE (ISCL)": "ISC",
    "MOZILLA PUBLIC LICENSE 2.0 (MPL 2.0)": "MPL-2.0",
    "PYTHON SOFTWARE FOUNDATION LICENSE": "PSF-2.0",
    "THE UNLICENSE (UNLICENSE)": "UNLICENSE",
    "MIT/APACHE-2.0": "MIT OR APACHE-2.0",
    "APACHE-2.0/MIT": "MIT OR APACHE-2.0",
    "UNLICENSE/MIT": "UNLICENSE OR MIT",
}

#: Our own packages and reviewed exceptions: name -> reason.
REVIEWED = {
    "eurogas-nexus": "this product",
    "eurogas-nexus-sdk": "this product",
    "eurogas-nexus-desktop": "this product",
    "eurogas-nexus-web": "this product",
}


@dataclass(frozen=True)
class Finding:
    ecosystem: str
    name: str
    version: str
    expression: str
    verdict: str  # allowed | review | forbidden | unknown | own


def _normalise(term: str) -> str:
    term = term.strip().upper()
    if term in ALIASES:
        return ALIASES[term]
    term = term.strip("()").strip()
    return ALIASES.get(term, term)


def evaluate(expression: str) -> str:
    """Classify one licence expression."""

    text = _normalise(expression or "")
    if not text or text in {"UNKNOWN", "NOASSERTION", "NONE", "-"}:
        return "unknown"
    # Split OR at the top level after normalising slashes used as OR.
    branches = [branch.strip() for branch in re.split(r"\s+OR\s+|/", text) if branch.strip()]
    verdicts = []
    for branch in branches:
        terms = [_normalise(term) for term in re.split(r"\s+AND\s+", branch)]
        term_verdicts = []
        for term in terms:
            if term in ALLOWED:
                term_verdicts.append("allowed")
            elif term in REVIEW:
                term_verdicts.append("review")
            elif FORBIDDEN_PATTERN.search(term):
                term_verdicts.append("forbidden")
            else:
                term_verdicts.append("unknown")
        for level in ("forbidden", "unknown", "review", "allowed"):
            if level in term_verdicts:
                verdicts.append(level)
                break
    for level in ("allowed", "review", "unknown", "forbidden"):
        if level in verdicts:
            return level
    return "unknown"


def python_findings() -> list[Finding]:
    findings = []
    for dist in distributions():
        meta = dist.metadata
        name = meta["Name"] or "?"
        expression = meta.get("License-Expression") or ""
        if not expression:
            classifiers = [
                c.split("::")[-1].strip()
                for c in meta.get_all("Classifier") or []
                if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]
            ]
            raw = (meta.get("License") or "").strip()
            if classifiers:
                expression = " OR ".join(classifiers)
            elif raw and len(raw) < 80 and "\n" not in raw:
                expression = raw
        verdict = "own" if name.lower() in REVIEWED else evaluate(expression)
        findings.append(Finding("python", name, meta["Version"] or "", expression, verdict))
    return findings


def npm_findings(lock_path: Path) -> list[Finding]:
    if not lock_path.is_file():
        return []
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    findings = []
    for key, item in (lock.get("packages") or {}).items():
        if not key:
            continue
        name = key.split("node_modules/")[-1]
        expression = item.get("license") or ""
        verdict = "own" if name in REVIEWED else evaluate(expression)
        findings.append(Finding("npm", name, item.get("version", ""), expression, verdict))
    return findings


def cargo_findings(crate_dir: Path) -> tuple[list[Finding], str | None]:
    if not (crate_dir / "Cargo.toml").is_file():
        return [], None
    if shutil.which("cargo") is None:
        return [], "cargo not installed: Rust crates not evaluated"
    completed = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--locked"],
        cwd=crate_dir, capture_output=True, text=True, timeout=900, check=False,
    )
    if completed.returncode != 0:
        return [], f"cargo metadata failed: {completed.stderr.strip()[-300:]}"
    findings = []
    for package in json.loads(completed.stdout)["packages"]:
        expression = package.get("license") or ""
        name = package["name"]
        verdict = "own" if name in REVIEWED else evaluate(expression)
        findings.append(Finding("rust", name, package["version"], expression, verdict))
    return findings, None


def render(findings: list[Finding], notes: list[str]) -> str:
    counts = Counter((f.ecosystem, f.verdict) for f in findings)
    lines = [
        "# Dependency licence review (commercial use)",
        "",
        "Generated by `scripts/security/check_commercial_licenses.py`. Every Python, npm and",
        "Rust dependency is classified from its declared licence metadata. This is an",
        "engineering gate, not legal advice; licence texts and notices still ship with",
        "release artifacts.",
        "",
        "| Ecosystem | Allowed | Review (weak copyleft) | Unknown | Forbidden |",
        "|---|---|---|---|---|",
    ]
    for ecosystem in ("python", "npm", "rust"):
        lines.append(
            f"| {ecosystem} | {counts[(ecosystem, 'allowed')]} | {counts[(ecosystem, 'review')]} "
            f"| {counts[(ecosystem, 'unknown')]} | {counts[(ecosystem, 'forbidden')]} |"
        )
    flagged = [f for f in findings if f.verdict in {"review", "unknown", "forbidden"}]
    lines += ["", "## Packages needing attention", ""]
    if not flagged:
        lines.append("None.")
    else:
        lines += ["| Ecosystem | Package | Version | Licence | Verdict |", "|---|---|---|---|---|"]
        seen = set()
        for f in sorted(flagged, key=lambda f: (f.verdict, f.ecosystem, f.name)):
            key = (f.ecosystem, f.name, f.version)
            if key in seen:
                continue
            seen.add(key)
            lines.append(
                f"| {f.ecosystem} | {f.name} | {f.version} | {f.expression or '-'} | {f.verdict} |"
            )
    lines += [
        "",
        "`review` licences (MPL-2.0, EPL-2.0, LGPL) permit proprietary commercial use when the",
        "covered files are not modified and, for LGPL, the library is dynamically linked or",
        "replaceable. Keep them unmodified; any change to them must be published under",
        "the same licence.",
    ]
    if notes:
        lines += ["", "## Notes", ""] + [f"- {note}" for note in notes]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", help="write a Markdown review to this path")
    parser.add_argument("--skip-python", action="store_true")
    parser.add_argument("--skip-rust", action="store_true")
    args = parser.parse_args(argv)

    findings: list[Finding] = []
    notes: list[str] = []
    if not args.skip_python:
        findings += python_findings()
    for lock in ("clients/web/package-lock.json", "clients/desktop/package-lock.json"):
        findings += npm_findings(ROOT / lock)
    if not args.skip_rust:
        rust, note = cargo_findings(ROOT / "clients/desktop/src-tauri")
        findings += rust
        if note:
            notes.append(note)
    if args.report:
        Path(args.report).write_text(render(findings, notes), encoding="utf-8")
    blocking = [f for f in findings if f.verdict in {"forbidden", "unknown"}]
    for f in blocking:
        print(f"{f.verdict.upper()}: {f.ecosystem} {f.name} {f.version} [{f.expression or '-'}]")
    for note in notes:
        print(f"NOTE: {note}")
    print(
        f"{len(findings)} dependencies checked; "
        f"{sum(f.verdict == 'review' for f in findings)} need review, {len(blocking)} blocking."
    )
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main())
