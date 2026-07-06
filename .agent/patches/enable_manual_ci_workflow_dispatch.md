# Enable Manual CI Trigger

## Goal

Allow the `CI` workflow to be started manually from the GitHub Actions page, in addition to existing `pull_request` and `push` triggers.

This solves the current issue where commits made through the connector may not expose a fresh workflow run, while the workflow itself is otherwise valid.

## Target file

```text
.github/workflows/ci.yml
```

## Required change

Change the workflow trigger block from:

```yaml
on:
  pull_request:
  push:
    branches:
      - main
```

to:

```yaml
on:
  workflow_dispatch:
  pull_request:
  push:
    branches:
      - main
```

## Non-goals

Do not change CI jobs, dependency versions, Python version, Node version, test commands, build commands, artifact names, or release workflow behavior.

## Acceptance

After this patch is merged, GitHub should show a `Run workflow` button under:

```text
Actions -> CI
```

Use it to run the current checks manually.

The CI job set should remain:

```text
validate
web-client-build
```

Validation commands represented by CI remain:

```bash
ruff check .
pytest -q tests
npm --prefix clients/web run build
```
