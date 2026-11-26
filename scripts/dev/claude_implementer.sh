#!/usr/bin/env bash
# Run one bounded implementation task with the Claude model through the Claude Code CLI, billed to a Console API key.
#
#   scripts/dev/claude_implementer.sh <working-directory> <task-file> [max-turns]
#
# The agent works only inside <working-directory> (a git worktree) and follows the task in
# <task-file>. Its changes are reviewed and tested by the coordinator before any commit is
# merged (AGENTS.md rule 3). The key is read from a file outside the repository
# (IMPLEMENTER_ENV_FILE, which must define ANTHROPIC_CONSOLE_API_KEY) and is never printed (rule 12).
set -euo pipefail

usage="usage: claude_implementer.sh <working-directory> <task-file> [max-turns]"
workdir="${1:?$usage}"
task_file="${2:?$usage}"
max_turns="${3:-150}"
env_file="${IMPLEMENTER_ENV_FILE:?set IMPLEMENTER_ENV_FILE to a file outside the repository that defines ANTHROPIC_CONSOLE_API_KEY}"

[ -e "$workdir/.git" ] || { echo "not a git worktree: $workdir" >&2; exit 2; }
[ -f "$task_file" ] || { echo "no task file: $task_file" >&2; exit 2; }
top="$(cd "$workdir" && git rev-parse --show-toplevel)"
case "$(cd "$(dirname "$env_file")" && pwd)/" in
  "$top/"*) echo "the key file must be outside the repository" >&2; exit 2 ;;
esac

# shellcheck disable=SC1090
key="$(set -a; . "$env_file" >/dev/null 2>&1; printf '%s' "${ANTHROPIC_CONSOLE_API_KEY:-}")"
[ -n "$key" ] || { echo "ANTHROPIC_CONSOLE_API_KEY is not set in the key file" >&2; exit 2; }
model="${CLAUDE_IMPLEMENTER_MODEL:-claude-opus-5-5}"

cd "$workdir"
# The implementer is a separate tool run, not this session: it gets its own configuration
# directory and none of the calling session's provider settings (a cloud session's host-managed
# provider would otherwise override the endpoint and the key). The Console key goes as x-api-key;
# the session's own credentials are not passed on.
config_dir="${CLAUDE_IMPLEMENTER_CONFIG_DIR:-${TMPDIR:-/tmp}/claude-implementer-config}"
mkdir -p "$config_dir"
exec env -i \
  HOME="$HOME" PATH="$PATH" LANG="${LANG:-C.UTF-8}" TERM="${TERM:-dumb}" \
  HTTPS_PROXY="${HTTPS_PROXY:-}" https_proxy="${https_proxy:-${HTTPS_PROXY:-}}" \
  NO_PROXY="${NO_PROXY:-}" no_proxy="${no_proxy:-${NO_PROXY:-}}" \
  NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-}" SSL_CERT_FILE="${SSL_CERT_FILE:-}" \
  CLAUDE_CONFIG_DIR="$config_dir" \
  IS_SANDBOX=1 \
  ANTHROPIC_API_KEY="$key" \
  ANTHROPIC_MODEL="$model" \
  ANTHROPIC_SMALL_FAST_MODEL="$model" \
  claude -p "$(cat "$task_file")" \
    --model "$model" \
    --max-turns "$max_turns" \
    --dangerously-skip-permissions \
    --output-format json
