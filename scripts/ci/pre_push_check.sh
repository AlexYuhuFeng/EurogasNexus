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
python -m pytest -q -x -p no:cacheprovider tests/contract tests/unit
if [ -d clients/web/node_modules ]; then
  (cd clients/web && npx tsc --noEmit -p . && npm test --silent >/dev/null)
fi
echo "pre-push checks passed"
