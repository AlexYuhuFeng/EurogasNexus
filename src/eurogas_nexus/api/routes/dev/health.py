"""Development-only API health route for local diagnostics."""

from fastapi import APIRouter

router = APIRouter(tags=["dev-health"])


@router.get("/health")
def dev_health() -> dict[str, str]:
    """Return development API shell status."""

    return {"status": "ok", "scope": "development"}
