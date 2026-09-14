# Autonomous runner controls

State flow: `RUNNING -> WAITING_ALLOWANCE -> RUNNING`, or `RUNNING -> WAITING_HUMAN|COMPLETE|STOPPED`.

- `WAITING_ALLOWANCE` is automatically retried.
- `WAITING_HUMAN` is never auto-cleared.
- Create `.automation/STOP` for an immediate clean stop on the next loop boundary.
- Runtime: `.automation/runtime/`
- Logs: `.automation/logs/`
- DeepSeek bridge uses isolated `.automation/runtime/codex-deepseek-home/`.

Optional native role installer: `python .automation/scripts/install_native_role.py --yes`. Keep bridge mode until native cross-provider handoff is verified on your exact Codex release.
