#!/bin/bash
# deploy-vps.sh - pixx.io Bulk-Editor auf dem VPS deployen (Forgejo-Registry + Traefik)
#
#   ./deploy-vps.sh              # Image ziehen und neu starten
#   ./deploy-vps.sh --backup     # vorher eine Sicherung erstellen (Empfehlung bei Updates)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

COMPOSE_FILE="docker-compose.vps.yml"
ENV_FILE=".env"
CONTAINER="pixxio-bulkedit-vps"

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose "$@"
    elif command -v docker-compose >/dev/null 2>&1; then
        docker-compose "$@"
    else
        echo -e "${RED}ERROR: Neither 'docker compose' nor 'docker-compose' is available${NC}"
        exit 1
    fi
}

read_env_var() {
    local key="$1"
    local raw
    raw=$(sed -n "s/^${key}=//p" "$ENV_FILE" | head -n 1 | sed 's/\r$//')
    if [ "${raw#\"}" != "$raw" ] && [ "${raw%\"}" != "$raw" ]; then
        raw="${raw#\"}"; raw="${raw%\"}"
    elif [ "${raw#\'}" != "$raw" ] && [ "${raw%\'}" != "$raw" ]; then
        raw="${raw#\'}"; raw="${raw%\'}"
    fi
    printf '%s' "$raw"
}

if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not installed${NC}"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    echo -e "${RED}ERROR: $COMPOSE_FILE not found${NC}"
    exit 1
fi

if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}ERROR: $ENV_FILE not found${NC}"
    echo -e "${YELLOW}Create it from .env.vps.example and set strong secrets.${NC}"
    exit 1
fi

if [ "$1" = "--backup" ]; then
    echo -e "${YELLOW}Sicherung vor dem Update...${NC}"
    ./backup.sh
fi

echo -e "${YELLOW}Logging in to Forgejo registry...${NC}"
docker login git.claudiapps.de

echo -e "${YELLOW}Validating compose configuration...${NC}"
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null

HOST_VALUE="$(read_env_var BULKEDIT_HOST)"
TRAEFIK_NETWORK_VALUE="$(read_env_var TRAEFIK_NETWORK)"

[ -z "$TRAEFIK_NETWORK_VALUE" ] && TRAEFIK_NETWORK_VALUE="him-net"

echo -e "${BLUE}Traefik host preflight:${NC}"
echo "  BULKEDIT_HOST=$HOST_VALUE"
echo "  TRAEFIK_NETWORK=$TRAEFIK_NETWORK_VALUE"

if [ -z "$HOST_VALUE" ]; then
    echo -e "${RED}ERROR: BULKEDIT_HOST is empty in $ENV_FILE${NC}"
    exit 1
fi

echo -e "${BLUE}Resolved Traefik router rules:${NC}"
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config | grep -E 'bulkedit\.rule|bulkedit-redirect\.rule' || true

if ! docker network inspect "$TRAEFIK_NETWORK_VALUE" >/dev/null 2>&1; then
    echo -e "${YELLOW}Creating missing external Docker network: $TRAEFIK_NETWORK_VALUE${NC}"
    docker network create "$TRAEFIK_NETWORK_VALUE" >/dev/null
fi

echo -e "${YELLOW}Pulling image from Forgejo...${NC}"
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull

echo -e "${YELLOW}Restarting containers (Migrationen laufen beim Start)...${NC}"
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down --remove-orphans
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d

echo -e "${YELLOW}Warte auf Healthcheck...${NC}"
for _ in $(seq 1 30); do
    STATE=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$STATE" = "healthy" ]; then
        break
    fi
    sleep 2
done
echo "  Health: $STATE"

echo -e "${GREEN}Container Status:${NC}"
compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps

echo -e "${GREEN}Deployed: https://${HOST_VALUE}${NC}"
echo -e "${BLUE}Logs: docker logs -f ${CONTAINER}${NC}"
echo -e "${BLUE}Nach einem Abbruch mitten im Schreiben: /runs oeffnen und 'Status abgleichen'.${NC}"
