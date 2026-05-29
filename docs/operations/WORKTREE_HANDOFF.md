# Worktree Handoff

## Decision

Use this Codex worktree as the authoritative documentation source until the new
handoff docs are committed or copied into the normal local checkout:

```text
C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
```

The normal human/Claude working checkout is:

```text
C:\Users\qqshu\Documents\Eurogasnexus
```

At inspection time, `C:\Users\qqshu\Documents\Eurogasnexus` existed and was a
Git checkout of `https://github.com/AlexYuhuFeng/EurogasNexus.git` on branch
`milestone-1-setup`.

It did not contain:

- `CLAUDE_CODE_START_HERE.md`;
- `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`;
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`;
- the full release docs under `docs/release/`.

It also contained uncommitted work:

```text
M  docs/contracts/04_DB_CONTRACT.md
M  docs/contracts/05_RUNTIME_STORE_CONTRACT.md
M  src/eurogas_nexus/db/__init__.py
M  src/eurogas_nexus/runtime_store/contracts.py
?? .claude/
?? data/milestone_2/
?? docs/operations/DB_RUNTIME_HARDENING.md
?? docs/operations/LIVE_POSTGRESQL_V1.md
?? scripts/ops/validate_v1_runtime_db.py
?? src/eurogas_nexus/db/health.py
?? src/eurogas_nexus/db/registry.py
?? tests/contract/test_db_runtime_hardening.py
?? tests/integration/test_alembic_import_safe.py
?? tests/integration/test_db_config.py
?? tests/integration/test_db_health.py
?? tests/security/test_db_url_redaction.py
```

Therefore the Documents checkout is not an empty duplicate and must not be deleted automatically.
It is an implementation checkout with work to review, merge, or intentionally
archive.

Claude Code must not be started there for V1 implementation until the handoff
docs are synced.

## Ambiguity Removal Decision

Do not keep two active roots indefinitely.

Current rule:

- Authoritative docs source: `C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus`
- Dirty implementation checkout to reconcile:
  `C:\Users\qqshu\Documents\Eurogasnexus`

Required cleanup path:

1. Review the uncommitted Documents work.
2. Port useful implementation changes into the authoritative worktree or commit
   them in Documents after syncing the docs.
3. After useful work is preserved, either:
   - make Documents the single normal working checkout; or
   - archive/delete Documents intentionally.

Do not delete `C:\Users\qqshu\Documents\Eurogasnexus` before step 1 unless the
user explicitly confirms that losing the uncommitted work is acceptable.

## Required Sync Rule

Before using `C:\Users\qqshu\Documents\Eurogasnexus` for Claude Code:

1. ensure this Codex worktree has the final docs;
2. copy or commit the docs into the Documents checkout;
3. verify the required files exist in Documents;
4. start Claude from Documents only after verification succeeds.

## Verification In Documents

Run from PowerShell:

```powershell
cd C:\Users\qqshu\Documents\Eurogasnexus
Test-Path .\CLAUDE_CODE_START_HERE.md
Test-Path .\docs\architecture\CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md
Test-Path .\docs\architecture\CLAUDE_CODE_MASTER_EXECUTION_INDEX.md
Test-Path .\docs\product\REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md
Test-Path .\docs\release\V1_RELEASE_MILESTONE_BACKLOG.md
```

All five checks must print `True`.

## Git Safe Directory Note

Codex sandbox inspection saw Git's `dubious ownership` warning for the Documents
checkout because the sandbox user differs from the desktop user. If Claude Code
CLI sees the same warning, run this once in that Claude environment:

```powershell
git config --global --add safe.directory C:/Users/qqshu/Documents/EurogasNexus
```

Do not use this command for unrelated repositories.

## Recommended Claude Location

For immediate work, start Claude here:

```powershell
cd C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
claude --dangerously-skip-permissions --add-dir "C:\Users\qqshu\Desktop" --add-dir "C:\Users\qqshu\Documents\Eurogasnexus"
```

After syncing docs into Documents, start Claude there:

```powershell
cd C:\Users\qqshu\Documents\Eurogasnexus
claude --dangerously-skip-permissions --add-dir "C:\Users\qqshu\Desktop"
```

`C:\Users\qqshu\Desktop` remains reference evidence only. Do not copy archived
source, credentials, raw/vendor/internal data, generated reports, or historical
artifacts into the active repo.
