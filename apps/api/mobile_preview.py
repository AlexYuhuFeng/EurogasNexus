"""Same-origin UI/API entry point for an isolated, disposable mobile preview."""

import os
from pathlib import Path

from fastapi.staticfiles import StaticFiles

from apps.api.main import app

if os.environ.get("EUROGAS_NEXUS_MOBILE_PREVIEW") != "1":
    raise RuntimeError("Explicit isolated mobile-preview acknowledgement required")
if os.environ.get("EUROGAS_NEXUS_ENV") != "test":
    raise RuntimeError("Mobile preview requires its own test environment and database")
if os.environ.get("EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS", "0") != "0":
    raise RuntimeError("Mobile preview must retain authentication")

web_root = Path(__file__).resolve().parents[2] / "clients" / "web" / "dist"
if not (web_root / "index.html").is_file():
    raise RuntimeError("Build the web client before starting the mobile preview")


app.mount("/", StaticFiles(directory=web_root, html=True), name="mobile-preview-ui")
