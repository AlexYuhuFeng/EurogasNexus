"""Public API surface stability gate (S4.1 contract evolution policy).

The stable unversioned `/api` surface is a product contract shared by Web, SDK,
CLI, Desktop, and documentation. Adding or removing a public path is a
breaking change for all five surfaces, so it must be declared here deliberately
and mirrored in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`.

Update process: edit `REVIEWED_PUBLIC_PATHS` in
`src/eurogas_nexus/security/public_surface.py`, update the policy document, then
run this test and `tests/contract/test_architecture_alignment.py` (which pins
the documented route count) in the same change.
"""

from apps.api.main import app
from eurogas_nexus.security.public_surface import REVIEWED_PUBLIC_PATHS

PINNED_PUBLIC_PATHS = REVIEWED_PUBLIC_PATHS

DECLARED_PREFIXES = ("/api/", "/api/internal/", "/api/dev/")


def _openapi_paths() -> set[str]:
    return set(app.openapi()["paths"])


def test_public_api_surface_is_exactly_the_pinned_set() -> None:
    paths = _openapi_paths()
    added = sorted(paths - PINNED_PUBLIC_PATHS)
    removed = sorted(PINNED_PUBLIC_PATHS - paths)
    assert added == [], (
        "Public paths added without contract declaration "
        "(update PINNED_PUBLIC_PATHS and API_CONTRACT_EVOLUTION_POLICY): " + ", ".join(added)
    )
    assert removed == [], "Public paths removed without contract declaration: " + ", ".join(removed)


def test_no_versioned_path_aliases_are_served() -> None:
    for path in _openapi_paths():
        assert not path.startswith("/v1"), f"Legacy versioned alias: {path}"
        assert not path.startswith("/api/v1"), f"Legacy versioned alias: {path}"


def test_every_path_uses_a_declared_profile_prefix() -> None:
    for path in _openapi_paths():
        assert path.startswith(DECLARED_PREFIXES), f"Undeclared path prefix: {path}"
