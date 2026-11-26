#!/usr/bin/env bash
# Run one bounded implementation task with the DeepSeek model through the Claude Code CLI.
#
#   scripts/dev/deepseek_implementer.sh <working-directory> <task-file> [max-turns]
#
# The agent works only inside <working-directory> (a git worktree) and follows the task in
# <task-file>. Its changes are reviewed and tested by the coordinator before any commit is
# merged (AGENTS.md rule 3). The key is read from a file outside the repository
# (DEEPSEEK_ENV_FILE, which must define DEEPSEEK_API_KEY) and is never printed (rule 12).
set -euo pipefail

usage="usage: deepseek_implementer.sh <working-directory> <task-file> [max-turns]"
workdir="${1:?$usage}"
task_file="${2:?$usage}"
max_turns="${3:-150}"
env_file="${DEEPSEEK_ENV_FILE:?set DEEPSEEK_ENV_FILE to a file outside the repository that defines DEEPSEEK_API_KEY}"

[ -e "$workdir/.git" ] || { echo "not a git worktree: $workdir" >&2; exit 2; }
[ -f "$task_file" ] || { echo "no task file: $task_file" >&2; exit 2; }
top="$(cd "$workdir" && git rev-parse --show-toplevel)"
case "$(cd "$(dirname "$env_file")" && pwd)/" in
  "$top/"*) echo "the key file must be outside the repository" >&2; exit 2 ;;
esac

# shellcheck disable=SC1090
key="$(set -a; . "$env_file" >/dev/null 2>&1; printf '%s' "${DEEPSEEK_API_KEY:-}")"
[ -n "$key" ] || { echo "DEEPSEEK_API_KEY is not set in the key file" >&2; exit 2; }
model="${DEEPSEEK_MODEL:-deepseek-flash}"

cd "$workdir"
exec env -u ANTHROPIC_API_KEY -u CLAUDE_CODE_OAUTH_TOKEN \
  ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
  ANTHROPIC_AUTH_TOKEN="$key" \
  ANTHROPIC_MODEL="$model" \
  ANTHROPIC_SMALL_FAST_MODEL="$model" \
  claude -p "$(cat "$task_file")" \
    --model "$model" \
    --max-turns "$max_turns" \
    --dangerously-skip-permissions \
    --output-format json
