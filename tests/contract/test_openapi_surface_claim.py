"""Keep the documented OpenAPI surface figure equal to the measured one.

Why this test exists
--------------------
`docs/release/RELEASE_READINESS.md` and `docs/release/SECURITY_ACCEPTANCE_EVIDENCE.md`
both stated "163 paths". The application had grown to 182, and nothing compared the
claim with the code, so the figure drifted by 19 paths unnoticed until a reviewer
counted for themselves. That is the failure mode this test removes: a number in a
release document that no command backs.

The assertion is a comparison, not a constant. Hard-coding "182" here would recreate
the same problem one layer down — it would pass while both the document and the
application moved together away from reality. Instead the test reads the figure out of
the document and requires it to equal what the application actually publishes, so it
fails when either side changes alone. That is the situation a reviewer needs to be
told about.

The count is a *surface* claim in a security-evidence document, so it is worth being
exact about: it bounds what an unauthenticated caller can reach and what each path must
declare. A stale figure there is not cosmetic.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
READINESS = REPO_ROOT / "docs" / "release" / "RELEASE_READINESS.md"
EVIDENCE = REPO_ROOT / "docs" / "release" / "SECURITY_ACCEPTANCE_EVIDENCE.md"

#: Both documents state the path count in this shape: "**N paths**" / "N paths / M operations".
_READINESS_FIGURE = re.compile(r"\*\*(\d+) paths / (\d+) operations\*\*")
_EVIDENCE_FIGURE = re.compile(r"\((\d+) paths / (\d+) operations as measured")


@pytest.fixture(scope="module")
def measured() -> tuple[int, int]:
    """Return (paths, operations) from the application itself."""

    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))

    from apps.api.main import app  # noqa: PLC0415

    schema = app.openapi()
    paths = schema["paths"]
    return len(paths), sum(len(operations) for operations in paths.values())


def test_readiness_states_the_measured_surface(measured: tuple[int, int]) -> None:
    """The release-readiness figure must equal what the application publishes."""

    text = READINESS.read_text(encoding="utf-8")
    match = _READINESS_FIGURE.search(text)
    assert match, (
        "RELEASE_READINESS.md no longer states the surface as "
        "'**N paths / M operations**'. Keep the shape, or update this test with it — "
        "the point is that the document carries a figure a test can compare."
    )
    documented = (int(match.group(1)), int(match.group(2)))
    assert documented == measured, (
        f"RELEASE_READINESS.md claims {documented[0]} paths / {documented[1]} operations "
        f"but the application publishes {measured[0]} paths / {measured[1]} operations. "
        "Update the document (and this is the drift that went unnoticed for 19 paths)."
    )


def test_security_evidence_states_the_measured_surface(measured: tuple[int, int]) -> None:
    """The security-evidence figure must agree with the application too."""

    text = EVIDENCE.read_text(encoding="utf-8")
    match = _EVIDENCE_FIGURE.search(text)
    assert match, (
        "SECURITY_ACCEPTANCE_EVIDENCE.md no longer states the surface as "
        "'(N paths / M operations as measured...)'. Keep the shape so it stays checkable."
    )
    documented = (int(match.group(1)), int(match.group(2)))
    assert documented == measured, (
        f"SECURITY_ACCEPTANCE_EVIDENCE.md claims {documented[0]} paths / "
        f"{documented[1]} operations but the application publishes {measured[0]} / "
        f"{measured[1]}."
    )


def test_the_two_documents_agree_with_each_other(measured: tuple[int, int]) -> None:
    """One figure, two readers: a disagreement means one of them is stale."""

    readiness = _READINESS_FIGURE.search(READINESS.read_text(encoding="utf-8"))
    evidence = _EVIDENCE_FIGURE.search(EVIDENCE.read_text(encoding="utf-8"))
    assert readiness and evidence, "one of the two documents lost its surface figure"
    assert (int(readiness.group(1)), int(readiness.group(2))) == (
        int(evidence.group(1)),
        int(evidence.group(2)),
    ), (
        "the two documents state different surface figures, so at least one is stale: "
        f"readiness={readiness.group(0)!r} evidence={evidence.group(0)!r}"
    )
