#!/usr/bin/env bash
# Fast gates to run before every push (install: ln -s ../../scripts/ci/pre_push_check.sh .git/hooks/pre-push).
#
# Main once broke because a commit imported a module that existed only in the author's
# working tree: every local test passed, the clean CI checkout could not import it. This
# hook refuses untracked source files and runs the quick checks a clean checkout would.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

untracked=$(git ls-files --others --exclude-standard -- src scripts tests apps packages clients/web/src clients/web/tests alembic | grep -E '\.(py|ts|tsx|mjs|css|json)$' || true)
if [ -n "$untracked" ]; then
  echo "Refusing push: untracked source files would be missing from the pushed commit:" >&2
  echo "$untracked" >&2
  echo "Commit them, delete them, or add them to .gitignore." >&2
  exit 1
fi

python -m ruff check .
python -c "from apps.api.main import app; assert app.openapi()['paths']"
# Hosted CI installs only from the hash-pinned locks into a clean canonical Python: a dependency
# declared but not locked for that interpreter fails there and nowhere else (2026-11-26).
python scripts/ci/check_lock_completeness.py
# The fast test directories, in parallel worker processes (pytest-xdist, `-n auto`: one per CPU),
# the same invocation the hosted validate shards use. The hosted validate job runs all of tests/;
# the directories left out here (api, domain, ingestion, integration, db, uat) stay hosted-only,
# as do the PostgreSQL, browser, licence-evidence and native jobs; see
# docs/engineering/CI_AND_BRANCH_PROTECTION.md. tests/sdk was missing and let a server field
# the SDK model lacked reach main on 2026-11-26.
if ! python -c "import xdist" 2>/dev/null; then
  echo "pytest-xdist is missing from this environment (a dev dependency since 2026-11-27):" >&2
  echo "  python -m pip install --require-hashes -r requirements.lock" >&2
  exit 1
fi
python -m pytest -q -x -n auto -p no:cacheprovider tests/contract tests/unit tests/security tests/release \
  tests/evals tests/sdk tests/cli tests/docs tests/optimization tests/streaming tests/workflow
if [ -d clients/web/node_modules ]; then
  (cd clients/web && npx tsc --noEmit -p . && npm test --silent >/dev/null)
fi
echo "pre-push checks passed"
