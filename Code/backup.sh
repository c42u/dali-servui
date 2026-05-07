#!/usr/bin/env bash
# =============================================================================
# DALI ServUI – Backup-Skript
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Erstellt ein Backup der DALI ServUI Konfiguration und Daten.
# Aufruf: ./backup.sh [ZIELVERZEICHNIS]
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
APP_NAME="dali-servui"
BACKUP_DIR="${1:-/tmp/${APP_NAME}-backup}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/${APP_NAME}_backup_${TIMESTAMP}.tar.gz"

# Moegliche Datenverzeichnisse
DATA_DIRS=(
    "/var/lib/${APP_NAME}"          # Linux-Installation
    "/opt/${APP_NAME}/data"         # Alternative
)

# Docker-Volume (falls vorhanden)
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
# Backup
# ---------------------------------------------------------------------------
main() {
    info "DALI ServUI Backup – ${TIMESTAMP}"

    # Zielverzeichnis anlegen
    mkdir -p "${BACKUP_DIR}"

    # Temporaeres Verzeichnis fuer Backup-Inhalt
    TEMP_DIR=$(mktemp -d)
    trap 'rm -rf "${TEMP_DIR}"' EXIT

    FOUND=0

    # Daten-Verzeichnisse sichern
    for dir in "${DATA_DIRS[@]}"; do
        if [ -d "${dir}" ]; then
            info "Sichere Datenverzeichnis: ${dir}"
            cp -r "${dir}" "${TEMP_DIR}/data"
            FOUND=1
            break
        fi
    done

    # Docker-Volume sichern (falls vorhanden)
    if command -v docker &>/dev/null; then
        if docker volume inspect "${DOCKER_VOLUME}" &>/dev/null; then
            info "Sichere Docker-Volume: ${DOCKER_VOLUME}"
            mkdir -p "${TEMP_DIR}/docker-data"
            docker run --rm \
                -v "${DOCKER_VOLUME}:/source:ro" \
                -v "${TEMP_DIR}/docker-data:/backup" \
                alpine:latest \
                sh -c "cp -r /source/* /backup/"
            FOUND=1
        fi
    fi

    if [ "${FOUND}" -eq 0 ]; then
        warn "Keine Datenverzeichnisse gefunden."
        warn "Moegliche Pfade: ${DATA_DIRS[*]}"
        warn "Docker-Volume: ${DOCKER_VOLUME}"
        exit 1
    fi

    # Metadaten hinzufuegen
    cat > "${TEMP_DIR}/backup_info.txt" <<EOF
DALI ServUI Backup
Datum: $(date -Is)
Hostname: $(hostname)
Version: 1.0.0
EOF

    # Archiv erstellen
    info "Erstelle Archiv: ${BACKUP_FILE}"
    tar -czf "${BACKUP_FILE}" -C "${TEMP_DIR}" .

    info "Backup abgeschlossen: ${BACKUP_FILE}"
    info "Groesse: $(du -h "${BACKUP_FILE}" | cut -f1)"
}

main "$@"
