#!/usr/bin/env bash
# List, and with --apply delete, the legacy 0.5 preview pre-releases and their tags.
#
# The 0.5.0 line published one GitHub pre-release per build, tagged
# v0.5-preview-<run>-<sha>; they crowd the Releases page and are rejected as release tags
# (docs/release/RELEASE_CHANNELS.md). Only tags matching that legacy pattern are touched;
# vX.Y.Z and vX.Y.Z-rc.N are never matched. Needs the GitHub CLI signed in with write
# access. Deleting a release removes its downloads: keep a copy of any build a customer
# still runs before applying.
#
#   bash scripts/release/prune_legacy_prereleases.sh            # list only
#   bash scripts/release/prune_legacy_prereleases.sh --apply    # delete releases and tags
#   KEEP=v0.5-preview-107-df3bde9 bash ... --apply              # keep one, e.g. the last
set -euo pipefail

REPO="${REPO:-AlexYuhuFeng/EurogasNexus}"
PATTERN='^v0\.5-preview-[0-9]+-[0-9a-f]{7,40}$'
APPLY="${1:-}"

mapfile -t TAGS < <(
  gh api --paginate "repos/${REPO}/tags" --jq '.[].name' | grep -E "${PATTERN}" | sort -V
)
echo "${#TAGS[@]} legacy preview tags in ${REPO}"
for tag in "${TAGS[@]}"; do
  if [[ -n "${KEEP:-}" && "${tag}" == "${KEEP}" ]]; then
    echo "keep    ${tag}"
    continue
  fi
  if [[ "${APPLY}" == "--apply" ]]; then
    gh release delete "${tag}" --repo "${REPO}" --yes --cleanup-tag 2>/dev/null \
      || gh api -X DELETE "repos/${REPO}/git/refs/tags/${tag}"
    echo "deleted ${tag}"
  else
    echo "would delete ${tag}"
  fi
done
[[ "${APPLY}" == "--apply" ]] || echo "Dry run. Re-run with --apply to delete."
