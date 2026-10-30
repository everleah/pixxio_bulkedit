#!/bin/bash
# restore.sh - Sicherung pruefen oder in eine (auch leere) Umgebung zurueckspielen
#
#   bash restore.sh --check                      # neueste Sicherung nur pruefen
#   bash restore.sh --check backups/datei.tar.gz.enc
#   bash restore.sh backups/datei.tar.gz.enc     # Container stoppen, Daten ersetzen
#
# Der Container bleibt waehrend des Zurueckspielens gestoppt; danach startet er neu und
# fuehrt ausstehende Migrationen aus. Bereits in pixx.io wirksame Aenderungen kommen
# durch einen Restore nicht zurueck und verschwinden nicht.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

CONTAINER="${BULKEDIT_CONTAINER:-pixxio-bulkedit-vps}"
VOLUME="${BULKEDIT_VOLUME:-pixxio_bulkedit_bulkedit_data}"
KEY_FILE="${BACKUP_KEY_FILE:-./backup.key}"
IMAGE="${BULKEDIT_IMAGE:-python:3.14-slim}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
MODE="restore"
ARCHIVE=""

while [ $# -gt 0 ]; do
    case "$1" in
        --check) MODE="check" ;;
        *) ARCHIVE="$1" ;;
    esac
    shift
done

if [ -z "$ARCHIVE" ]; then
    ARCHIVE=$(ls -1t "$BACKUP_DIR"/*.tar.gz.enc 2>/dev/null | head -n 1 || true)
    if [ -z "$ARCHIVE" ]; then
        echo -e "${RED}ERROR: Keine Sicherung in ${BACKUP_DIR} gefunden.${NC}"
        echo -e "${YELLOW}Aufruf: bash restore.sh [--check] [datei]${NC}"
        ls -1t "$BACKUP_DIR" 2>/dev/null | head -n 5
        exit 1
    fi
    echo -e "${YELLOW}Verwende neueste Sicherung: $ARCHIVE${NC}"
fi

if [ ! -f "$ARCHIVE" ]; then
    echo -e "${RED}ERROR: Sicherungsdatei nicht gefunden: $ARCHIVE${NC}"
    exit 1
fi

if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}ERROR: Schluesseldatei $KEY_FILE fehlt${NC}"
    exit 1
fi

WORKDIR="$(mktemp -d)"
cleanup() { rm -rf "$WORKDIR"; }
trap cleanup EXIT

echo -e "${YELLOW}Entschluesseln und entpacken...${NC}"
openssl enc -d -aes-256-cbc -pbkdf2 -pass "file:$KEY_FILE" -in "$ARCHIVE" | tar -C "$WORKDIR" -xzf -

if [ ! -f "$WORKDIR/bulkedit.sqlite3" ]; then
    echo -e "${RED}ERROR: bulkedit.sqlite3 fehlt im Archiv${NC}"
    exit 1
fi

echo -e "${YELLOW}Integritaet pruefen...${NC}"
REPORT=$(cat "$WORKDIR/bulkedit.sqlite3" | docker run --rm -i "$IMAGE" python -c "
import sqlite3, sys, tempfile, os
path = os.path.join(tempfile.mkdtemp(), 'db.sqlite3')
with open(path, 'wb') as handle:
    handle.write(sys.stdin.buffer.read())
connection = sqlite3.connect(path)
print(connection.execute('PRAGMA integrity_check').fetchone()[0])
print(connection.execute(\"SELECT count(*) FROM sqlite_master WHERE type='table'\").fetchone()[0])
print(connection.execute('SELECT version_num FROM alembic_version').fetchone()[0])
")
INTEGRITY=$(echo "$REPORT" | sed -n 1p)
TABLES=$(echo "$REPORT" | sed -n 2p)
VERSION=$(echo "$REPORT" | sed -n 3p)
if [ "$INTEGRITY" != "ok" ]; then
    echo -e "${RED}ERROR: integrity_check: $INTEGRITY${NC}"
    exit 1
fi
echo -e "${GREEN}Integritaet ok: $TABLES Tabellen, Schema-Version $VERSION${NC}"

if [ "$MODE" = "check" ]; then
    echo -e "${GREEN}Sicherung ist lesbar und konsistent: $ARCHIVE${NC}"
    exit 0
fi

echo -e "${YELLOW}Container stoppen...${NC}"
docker stop "$CONTAINER" >/dev/null

echo -e "${YELLOW}Datenbank in Volume $VOLUME ersetzen...${NC}"
cat "$WORKDIR/bulkedit.sqlite3" | docker run --rm -i -v "$VOLUME:/data" "$IMAGE" sh -c \
    "rm -f /data/bulkedit.sqlite3-wal /data/bulkedit.sqlite3-shm && cat > /data/bulkedit.sqlite3"

echo -e "${YELLOW}Container starten (Migrationen laufen beim Start)...${NC}"
docker start "$CONTAINER" >/dev/null
STATE="unknown"
for _ in $(seq 1 30); do
    STATE=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "unknown")
    if [ "$STATE" = "healthy" ]; then
        break
    fi
    sleep 2
done

echo -e "${GREEN}Wiederherstellung abgeschlossen (Health: $STATE)${NC}"
echo -e "${YELLOW}Anschliessend in der App pruefen: Anmeldung, Profile, Arbeitsbestaende und /runs.${NC}"
echo -e "${YELLOW}Unklare Schreibauftraege nach dem Restore ueber /runs 'Status abgleichen' klaeren.${NC}"
