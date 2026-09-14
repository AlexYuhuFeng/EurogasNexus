# Integration assumptions checked 2026-09-14

- Codex supports user-defined model providers, multi-agent roles and non-interactive `codex exec` JSON output.
- GPT-6 Astra model id is `gpt-6-astra`; current guidance requires Codex CLI 0.153.0+.
- DeepSeek current Codex integration documentation uses `deepseek-flash`, Responses API compatibility and `https://api.deepseek.com/`; re-run preflight/review provider docs after major Codex or DeepSeek updates.
- Current Codex issue reports show cross-provider native-subagent regressions, so bridge mode is the default.
- Explicit `codex exec resume <thread_id>` is verified by checking the returned thread id because resume fallbacks have had bugs.
- Usage-limit errors often include `You've hit your usage limit` and an English `try again at ...`; the supervisor parses this when possible and otherwise probes conservatively.
