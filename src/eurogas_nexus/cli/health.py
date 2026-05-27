"""CLI-friendly health command helpers."""

from eurogas_nexus.sdk import fetch_health


def run_health_check(base_url: str) -> str:
    """Return compact health status string for operator usage."""

    payload = fetch_health(base_url)
    return (
        f"status={payload.status} service={payload.service} "
        f"version={payload.version} profile={payload.profile}"
    )
