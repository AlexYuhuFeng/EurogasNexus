"""Migrate a dedicated test database, provision its UAT login, then serve."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    required = {
        "EUROGAS_NEXUS_MOBILE_PREVIEW": "1",
        "EUROGAS_NEXUS_ENV": "test",
        "EUROGAS_NEXUS_API_PROFILE": "development",
        "EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED": "1",
        "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS": "0",
        "EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES": "0",
        "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "0",
    }
    for key, expected in required.items():
        if os.environ.get(key) != expected:
            raise RuntimeError(f"Isolated preview requires {key}={expected}")
    for key in (
        "DATABASE_URL",
        "EUROGAS_NEXUS_DEV_LOGIN_USERNAME",
        "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD",
    ):
        if not os.environ.get(key, "").strip():
            raise RuntimeError(f"Missing preview configuration: {key}")
    if len(os.environ["EUROGAS_NEXUS_DEV_LOGIN_PASSWORD"]) < 20:
        raise RuntimeError("Use a fresh preview password of at least 20 characters")
    # Render supplies postgresql://; pg8000 is the project's locked driver.
    dsn = os.environ["DATABASE_URL"]
    for prefix in ("postgres://", "postgresql://"):
        if dsn.startswith(prefix):
            dsn = "postgresql+pg8000://" + dsn[len(prefix):]
            break
    os.environ["RUNTIME_STORE_DATABASE_URL"] = dsn
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    subprocess.run([sys.executable, "scripts/uat/seed_browser_identity.py"], check=True)
    import uvicorn

    uvicorn.run(
        "apps.api.mobile_preview:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
