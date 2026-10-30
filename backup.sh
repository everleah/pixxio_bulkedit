#!/bin/bash
# backup.sh - konsistente Sicherung von Datenbank und Zustand des Bulk-Editors
#
#   ./backup.sh                       # sichert nach ./backups
#   ./backup.sh /pfad/ausserhalb/vps  # anderes Zielverzeichnis
#
# Gesichert werden:
#   - die SQLite-Datenbank als konsistente Kopie ueber die SQLite-Backup-API im
#     Container (funktioniert auch bei laufender Anwendung),
#   - die NiceGUI-Sitzungsdatei (enthaelt nur Sprache und Benutzer-ID).
#
# Die Sicherung wird mit OpenSSL (AES-256-CBC, PBKDF2) verschluesselt. Der Schluessel
# liegt in BACKUP_KEY_FILE (Standard: ./backup.key) und gehoert NICHT auf denselben
# Datentraeger wie die Sicherungen. Ohne Schluessel ist eine Sicherung wertlos.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

CONTAINER="${BULKEDIT_CONTAINER:-pixxio-bulkedit-vps}"
TARGET_DIR="${1:-./backups}"
KEY_FILE="${BACKUP_KEY_FILE:-./backup.key}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$TARGET_DIR/bulkedit-$STAMP.tar.gz.enc"
WORKDIR="$(mktemp -d)"

cleanup() {
    rm -rf "$WORKDIR"
    docker exec "$CONTAINER" rm -f /data/backup.sqlite3 >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker inspect "$CONTAINER" >/dev/null 2>&1; then
    echo -e "${RED}ERROR: Container $CONTAINER not found${NC}"
    exit 1
fi

if [ ! -f "$KEY_FILE" ]; then
    echo -e "${RED}ERROR: Schluesseldatei $KEY_FILE fehlt.${NC}"
    echo -e "${YELLOW}Einmal erzeugen und getrennt aufbewahren:${NC}"
    echo "  openssl rand -base64 48 > $KEY_FILE && chmod 600 $KEY_FILE"
    exit 1
fi

mkdir -p "$TARGET_DIR"

echo -e "${YELLOW}Konsistente Datenbankkopie im Container...${NC}"
docker exec -i "$CONTAINER" python - <<'PY'
import sqlite3

source = sqlite3.connect("/data/bulkedit.sqlite3")
target = sqlite3.connect("/data/backup.sqlite3")
with target:
    source.backup(target)
result = target.execute("PRAGMA integrity_check").fetchone()[0]
target.close()
source.close()
if result != "ok":
    raise SystemExit(f"integrity_check: {result}")
print("Kopie erstellt, integrity_check ok")
PY

echo -e "${YELLOW}Dateien aus dem Container holen...${NC}"
docker cp "$CONTAINER:/data/backup.sqlite3" "$WORKDIR/bulkedit.sqlite3"
mkdir -p "$WORKDIR/nicegui"
docker cp "$CONTAINER:/app/.nicegui/." "$WORKDIR/nicegui" 2>/dev/null || true

echo -e "${YELLOW}Archiv verschluesseln...${NC}"
tar -C "$WORKDIR" -czf - . | openssl enc -aes-256-cbc -pbkdf2 -salt -pass "file:$KEY_FILE" -out "$ARCHIVE"
chmod 600 "$ARCHIVE"

echo -e "${GREEN}Sicherung erstellt: $ARCHIVE${NC}"
echo -e "${BLUE}Groesse: $(du -h "$ARCHIVE" | cut -f1)${NC}"
echo -e "${YELLOW}Pruefen mit: ./restore.sh --check $ARCHIVE${NC}"
echo -e "${YELLOW}BULKEDIT_MASTER_KEY und BULKEDIT_STORAGE_SECRET aus .env getrennt sichern.${NC}"
