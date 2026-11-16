# syntax=docker/dockerfile:1
#
# HOSTED TEST/DEMO SERVER IMAGE - NOT the customer runtime.
#
# This image runs Eurogas Nexus as one container (deploy/demo/compose.yaml adds PostgreSQL):
# the API and the built web client on one port and one origin, with the fictional
# demo desk (every price and flow marked simulated), the reference network and the tester
# identities created at start-up. It deliberately contains the demo seed that the customer
# image excludes, and it refuses to run as a trial or release environment.
#
# The customer runtime image is deploy/runtime/Dockerfile.api (explicit script allowlist,
# artifact verification, licence texts); the release workflow builds only that file.
# Operator guide: docs/deployment/SELF_HOSTED_DEMO.md
#
# Build context: the repository root. Port: $PORT (default 8080).
# Health: /api/health/live (liveness), /api/health/ready (database and schema current).
# No build secret is required; `build_ca` is an optional CA for a TLS-intercepting proxy.

# --- Stage 1: the web client (static files only) --------------------------------------
FROM node:24-alpine@sha256:116b800c3754b440ee0aa3ed2f20f5bf3d99a554bfd9adeea09ea8017f6e85f5 AS web

WORKDIR /web
COPY clients/web/package.json clients/web/package-lock.json ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/build_ca; fi; \
    npm ci --no-audit --no-fund
COPY clients/web/ ./
RUN npm run build

# --- Stage 2: the project wheel from hash-pinned build dependencies --------------------
FROM python:3.11-alpine@sha256:03c8e956bf1eee7763faf3a9fbb24b3ff9c0496cc2dbc5bcb0d6ac1f6268a287 AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build
COPY requirements-build.lock requirements-runtime.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python -m pip install --no-cache-dir --require-hashes \
    -r requirements-build.lock \
    -r requirements-runtime.lock

COPY pyproject.toml setup.py README.md ./
COPY src ./src
COPY packages ./packages
RUN python -m pip wheel --no-deps --no-build-isolation . --wheel-dir /wheels

# --- Stage 3: runtime -------------------------------------------------------------------
FROM python:3.11-alpine@sha256:03c8e956bf1eee7763faf3a9fbb24b3ff9c0496cc2dbc5bcb0d6ac1f6268a287

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080

RUN addgroup -S eurogas \
    && adduser -S -G eurogas -h /home/eurogas eurogas

WORKDIR /app

# Locked dependencies first, so a source-only push reuses this layer.
COPY requirements-runtime.lock ./
RUN --mount=type=secret,id=build_ca \
    if [ -f /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    python -m pip install --no-cache-dir --require-hashes \
    -r requirements-runtime.lock

COPY --from=builder /wheels ./wheels
RUN python -m pip install --no-cache-dir --no-deps --no-index \
    --find-links ./wheels eurogas_nexus \
    && rm -rf ./wheels \
    && python -m pip uninstall --yes setuptools wheel

COPY alembic.ini ./
COPY alembic ./alembic
COPY apps ./apps
# Start-up, demo seed and the operator tools a test server needs (ingestion jobs,
# reference network). Demo-only content: never copy this list into the customer image.
COPY scripts/demo ./scripts/demo
COPY scripts/ops ./scripts/ops
COPY --from=web /web/dist ./web

# The commit this image was built from, reported by GET /api/runtime/release.
ARG GIT_SHA=""
ARG GIT_REF=""
ENV EUROGAS_NEXUS_BUILD_GIT_SHA=${GIT_SHA} \
    EUROGAS_NEXUS_BUILD_GIT_REF=${GIT_REF}
LABEL org.opencontainers.image.title="Eurogas Nexus hosted test/demo server" \
      org.opencontainers.image.description="Demo data only (simulated); not the customer runtime image" \
      org.opencontainers.image.revision="${GIT_SHA}"

RUN chown -R eurogas:eurogas /app
USER eurogas

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/api/health/live' % os.environ.get('PORT', '8080'), timeout=4)"

CMD ["python", "scripts/demo/start_public_demo.py", "serve"]
