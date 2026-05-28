"""Internal-only API health route for service operators."""

from fastapi import APIRouter

router = APIRouter(prefix="/internal", tags=["internal-health"])


@router.get("/health")
def internal_health() -> dict[str, str]:
    """Return internal API shell status."""

    return {"status": "ok", "scope": "internal"}
