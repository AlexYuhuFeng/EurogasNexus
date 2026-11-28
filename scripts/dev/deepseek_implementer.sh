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
# Reasoning effort: max by default (owner, 2026-11-27); DEEPSEEK_EFFORT overrides it.

cd "$workdir"
# The DeepSeek agent is a separate tool run, not this session: it gets its own configuration
# directory and none of the calling session's provider settings (a cloud session's host-managed
# provider would otherwise override the endpoint and the key). DeepSeek's Anthropic-compatible
# endpoint takes the key as x-api-key.
config_dir="${DEEPSEEK_CONFIG_DIR:-${TMPDIR:-/tmp}/deepseek-implementer-config}"
mkdir -p "$config_dir"
exec env -i \
  HOME="$HOME" PATH="$PATH" LANG="${LANG:-C.UTF-8}" TERM="${TERM:-dumb}" \
  HTTPS_PROXY="${HTTPS_PROXY:-}" https_proxy="${https_proxy:-${HTTPS_PROXY:-}}" \
  NO_PROXY="${NO_PROXY:-}" no_proxy="${no_proxy:-${NO_PROXY:-}}" \
  NODE_EXTRA_CA_CERTS="${NODE_EXTRA_CA_CERTS:-}" SSL_CERT_FILE="${SSL_CERT_FILE:-}" \
  CLAUDE_CONFIG_DIR="$config_dir" \
  IS_SANDBOX=1 \
  ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic" \
  ANTHROPIC_API_KEY="$key" \
  ANTHROPIC_MODEL="$model" \
  ANTHROPIC_SMALL_FAST_MODEL="$model" \
  claude -p "$(cat "$task_file")" \
    --model "$model" \
    --max-turns "$max_turns" \
    --effort "${DEEPSEEK_EFFORT:-max}" \
    --dangerously-skip-permissions \
    --output-format json
