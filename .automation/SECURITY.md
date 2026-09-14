# Security boundaries

- Never put `DEEPSEEK_API_KEY` in Git, prompts or task briefs.
- Headless work uses `approval_policy="never"` with `workspace-write` sandbox so it does not hang for approvals but still has a write boundary.
- No default `danger-full-access`.
- No auto-push or auto-merge.
- Do not run unattended automation on an untrusted repo.
- One active supervisor per working tree.
- Windows and Linux must not both be active against the same checkout.
- Native cross-provider subagents are optional because compatibility has changed across Codex releases.
