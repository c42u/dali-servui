#!/usr/bin/env bash
# =============================================================================
# DALI ServUI – Restore-Skript
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Stellt ein Backup der DALI ServUI Konfiguration wieder her.
# Aufruf: ./restore.sh <BACKUP-DATEI> [ZIELVERZEICHNIS]
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
APP_NAME="dali-servui"
BACKUP_FILE="${1:-}"
TARGET_DIR="${2:-/var/lib/${APP_NAME}}"
DOCKER_VOLUME="${APP_NAME}_dali-data"

# Farben
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
main() {
    if [ -z "${BACKUP_FILE}" ]; then
        error "Verwendung: $0 <BACKUP-DATEI> [ZIELVERZEICHNIS]"
        exit 1
    fi

    if [ ! -f "${BACKUP_FILE}" ]; then
        error "Backup-Datei nicht gefunden: ${BACKUP_FILE}"
        exit 1
    fi

    info "DALI ServUI Restore"
    info "Quelle: ${BACKUP_FILE}"

    # Temporaeres Verzeichnis fuer Entpacken
    TEMP_DIR=$(mktemp -d)
    trap 'rm -rf "${TEMP_DIR}"' EXIT

    # Archiv entpacken
    info "Entpacke Backup..."
    tar -xzf "${BACKUP_FILE}" -C "${TEMP_DIR}"

    # Backup-Info anzeigen
    if [ -f "${TEMP_DIR}/backup_info.txt" ]; then
        echo "---"
        cat "${TEMP_DIR}/backup_info.txt"
        echo "---"
    fi

    # Daten wiederherstellen
    if [ -d "${TEMP_DIR}/data" ]; then
        info "Stelle Daten wieder her nach: ${TARGET_DIR}"

        # Service stoppen (falls aktiv)
        if systemctl is-active "${APP_NAME}" &>/dev/null; then
            warn "Stoppe ${APP_NAME}-Service..."
            systemctl stop "${APP_NAME}"
        fi

        mkdir -p "${TARGET_DIR}"
        cp -r "${TEMP_DIR}/data/"* "${TARGET_DIR}/"

        # Berechtigungen setzen
        if id dali &>/dev/null; then
            chown -R dali:dali "${TARGET_DIR}"
        fi

        # Service wieder starten
        if systemctl is-enabled "${APP_NAME}" &>/dev/null; then
            info "Starte ${APP_NAME}-Service..."
            systemctl start "${APP_NAME}"
        fi
    fi

    # Docker-Volume wiederherstellen (falls vorhanden)
    if [ -d "${TEMP_DIR}/docker-data" ]; then
        if command -v docker &>/dev/null; then
            info "Stelle Docker-Volume wieder her: ${DOCKER_VOLUME}"

            # Container stoppen
            docker compose -f /opt/claude/dali-servui/Docker/docker-compose.yml down 2>/dev/null || true

            # Volume erstellen falls noetig
            docker volume create "${DOCKER_VOLUME}" 2>/dev/null || true

            # Daten kopieren
            docker run --rm \
                -v "${DOCKER_VOLUME}:/target" \
                -v "${TEMP_DIR}/docker-data:/source:ro" \
                alpine:latest \
                sh -c "cp -r /source/* /target/"

            info "Docker-Volume wiederhergestellt."
        fi
    fi

    info "Restore abgeschlossen."
}

main "$@"
