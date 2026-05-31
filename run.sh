#!/usr/bin/env bash
# Launcher for the Discord ACP Kiro bot container.
#
# Usage:
#   ./run.sh build            Build the image
#   ./run.sh up               Start the bot (detached); creates volumes if missing
#   ./run.sh login            Authenticate Kiro inside the container (device flow)
#   ./run.sh logs             Follow the bot logs
#   ./run.sh shell            Open an interactive shell in the container
#   ./run.sh stop | down      Stop / remove the container
#   ./run.sh restart          Restart the container
#
# The container runs as the non-root "bot" user and is locked down
# (no new privileges, all capabilities dropped, no Docker socket or host
# secrets mounted). Kiro auth/config/sessions persist in the "$VOL_HOME"
# volume; the working directory persists in "$VOL_WS".
set -euo pipefail

IMAGE="${IMAGE:-discord-acp-kiro:latest}"
CONTAINER="${CONTAINER:-discord-acp-kiro}"
VOL_HOME="${VOL_HOME:-kiro-acp-home}"
VOL_WS="${VOL_WS:-kiro-acp-workspace}"
ENV_FILE="${ENV_FILE:-.env}"

cd "$(dirname "$0")"

build() { docker build -t "$IMAGE" .; }

up() {
    [ -f "$ENV_FILE" ] || { echo "Missing $ENV_FILE (copy .env.example and set DISCORD_TOKEN)." >&2; exit 1; }
    docker volume create "$VOL_HOME" >/dev/null
    docker volume create "$VOL_WS" >/dev/null
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
    docker run -d \
        --name "$CONTAINER" \
        --env-file "$ENV_FILE" \
        --restart unless-stopped \
        --security-opt no-new-privileges \
        --cap-drop ALL \
        -v "$VOL_HOME:/home/bot/.kiro" \
        -v "$VOL_WS:/workspace" \
        "$IMAGE"
    echo "Started $CONTAINER. If Kiro is not authenticated yet, run: ./run.sh login"
}

login() { docker exec -it "$CONTAINER" kiro-cli login; }
logs()  { docker logs -f "$CONTAINER"; }
shell() { docker exec -it "$CONTAINER" bash -l; }
stop()  { docker stop "$CONTAINER"; }
down()  { docker rm -f "$CONTAINER"; }
restart() { docker restart "$CONTAINER"; }

case "${1:-up}" in
    build) build ;;
    up) up ;;
    login) login ;;
    logs) logs ;;
    shell) shell ;;
    stop) stop ;;
    down) down ;;
    restart) restart ;;
    *) echo "Usage: $0 {build|up|login|logs|shell|stop|down|restart}" >&2; exit 1 ;;
esac
