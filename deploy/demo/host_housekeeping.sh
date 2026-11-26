#!/usr/bin/env bash
# Host-level clean-up for the Eurogas Nexus demo server (not the product's database job).
#
# Install as a daily cron on the machine that runs deploy/demo/compose.yaml:
#
#   17 3 * * * /opt/eurogas-nexus/deploy/demo/host_housekeeping.sh \
#       >> /var/log/eurogas-demo-housekeeping.log 2>&1
#
# Run it as root (or a user in the docker group that can read the containers' log files).
# It is safe while the demo serves:
#
#   * it removes only *unused* images and build cache older than 24 hours - a running
#     container's image is in use and is never removed (no `docker image prune -a --force`
#     without the age filter, no `docker system prune`);
#   * it never touches a volume: the database volume `eurogas-nexus-demo-postgres` and the
#     Caddy volume are never named by any prune command;
#   * it never stops or removes a running container;
#   * log truncation is a fallback only. deploy/demo/compose.yaml already caps every service's
#     json-file log at 10 MB x 3; a container started before that cap (or by another compose
#     file) has its log truncated instead of deleted.
#
# Before it removes anything it prints the disk use, so the log shows the effect of one run.
# Exit status: 0 even when a single clean-up step fails (a cron job that fails every day is
# noise); a broken docker daemon is reported and the disk report still runs.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${DEMO_COMPOSE_FILE:-$SCRIPT_DIR/compose.yaml}"
PROJECT_NAME="${DEMO_PROJECT_NAME:-eurogas-nexus-demo}"
IMAGE_AGE="${DEMO_IMAGE_PRUNE_AGE:-24h}"
LOGGING_LIMIT_MB="${DEMO_LOG_LIMIT_MB:-10}"

say() { printf '[host-housekeeping] %s\n' "$*"; }

report_disk() {
    say "disk use:"
    df -h / 2>/dev/null || say "df /: not visible"
    if command -v docker >/dev/null 2>&1; then
        local docker_root
        docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
        if [ -n "$docker_root" ] && [ "$docker_root" != "/" ]; then
            df -h "$docker_root" 2>/dev/null || true
        fi
        local volume_mount
        volume_mount="$(docker volume inspect "${PROJECT_NAME}-postgres" \
            --format '{{.Mountpoint}}' 2>/dev/null || true)"
        if [ -n "$volume_mount" ]; then
            say "database volume:"
            df -h "$volume_mount" 2>/dev/null || true
            du -sh "$volume_mount" 2>/dev/null || true
        fi
        say "docker system df:"
        docker system df 2>/dev/null || true
    fi
}

truncate_uncapped_logs() {
    # Only the demo project's containers, and only those without a max-size cap.
    command -v docker >/dev/null 2>&1 || return 0
    local ids
    ids="$(docker ps -q \
        --filter "label=com.docker.compose.project=${PROJECT_NAME}" 2>/dev/null || true)"
    [ -n "$ids" ] || return 0
    local id name log_path max_size driver
    for id in $ids; do
        name="$(docker inspect --format '{{.Name}}' "$id" 2>/dev/null | sed 's#^/##')"
        driver="$(docker inspect --format '{{.HostConfig.LogConfig.Type}}' "$id" 2>/dev/null || true)"
        max_size="$(docker inspect \
            --format '{{index .HostConfig.LogConfig.Config "max-size"}}' "$id" 2>/dev/null || true)"
        [ "$driver" = "json-file" ] || continue
        [ -z "$max_size" ] || continue
        log_path="$(docker inspect --format '{{.LogPath}}' "$id" 2>/dev/null || true)"
        [ -n "$log_path" ] && [ -f "$log_path" ] || continue
        if truncate -s 0 "$log_path" 2>/dev/null; then
            say "truncated uncapped log of $name (compose caps new containers at ${LOGGING_LIMIT_MB}m)"
        else
            say "could not truncate $name's log (run as root or a docker-group user with file access)"
        fi
    done
}

say "start $(date -u '+%Y-%m-%dT%H:%M:%SZ') project=$PROJECT_NAME"
report_disk

if ! command -v docker >/dev/null 2>&1; then
    say "docker is not available; nothing removed"
    exit 0
fi

# Unused images and build cache older than 24 hours. A running container's image is in use,
# so it is not "unused" and this never removes a serving container's image.
say "pruning unused images older than $IMAGE_AGE"
docker image prune --all --force --filter "until=$IMAGE_AGE" 2>&1 || say "image prune failed"

say "pruning unused build cache older than $IMAGE_AGE"
docker builder prune --all --force --filter "until=$IMAGE_AGE" 2>&1 || say "builder prune failed"

truncate_uncapped_logs

say "after:"
report_disk
say "done"
exit 0
