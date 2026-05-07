#!/usr/bin/env bash
# =============================================================================
# DALI ServUI – Linux-Installationsskript
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Installiert DALI ServUI direkt auf einem Linux-System (ohne Docker).
# Getestet mit: Debian 12, Ubuntu 22.04+, Raspberry Pi OS
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
APP_NAME="dali-servui"
APP_DIR="/opt/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
VENV_DIR="${APP_DIR}/venv"
SERVICE_USER="dali"
SERVICE_GROUP="dali"
SYSTEMD_UNIT="/etc/systemd/system/${APP_NAME}.service"
UDEV_RULE_DALI="/etc/udev/rules.d/99-dali-servui.rules"

# Farben fuer Ausgabe
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ---------------------------------------------------------------------------
# Voraussetzungen pruefen
# ---------------------------------------------------------------------------
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        error "Dieses Skript muss als root ausgefuehrt werden."
        echo "  sudo $0 $*"
        exit 1
    fi
}

check_os() {
    if [ ! -f /etc/os-release ]; then
        error "Nicht unterstuetztes Betriebssystem."
        exit 1
    fi
    . /etc/os-release
    info "Betriebssystem: ${PRETTY_NAME}"
}

# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------
install_packages() {
    info "Installiere Systemabhaengigkeiten..."
    apt-get update -qq
    apt-get install -y -qq \
        python3 \
        python3-venv \
        python3-pip \
        libhidapi-hidraw0 \
        libhidapi-dev \
        libusb-1.0-0 \
        libusb-1.0-0-dev \
        pkg-config \
        build-essential
}

create_user() {
    if ! id "${SERVICE_USER}" &>/dev/null; then
        info "Erstelle Benutzer '${SERVICE_USER}'..."
        groupadd -r "${SERVICE_GROUP}" 2>/dev/null || true
        useradd -r -g "${SERVICE_GROUP}" -d "${APP_DIR}" -s /sbin/nologin "${SERVICE_USER}"
    else
        info "Benutzer '${SERVICE_USER}' existiert bereits."
    fi
    # Zusaetzliche Gruppen fuer Hardware-Zugriff (USB/FTDI)
    usermod -aG plugdev,dialout "${SERVICE_USER}" 2>/dev/null || true
}

setup_udev() {
    info "Richte udev-Regeln fuer DALI-Hardware ein..."

    # Alle DALI-Hardware-Regeln in einer Datei
    cat > "${UDEV_RULE_DALI}" <<'EOF'
# =============================================================================
# DALI ServUI – udev-Regeln fuer DALI-Hardware
# Zugriff fuer Gruppe 'dali' auf alle unterstuetzten Adapter
# =============================================================================

# Hasseb DALI USB Master – HID-Zugriff (hidraw)
KERNEL=="hidraw*", ATTRS{idVendor}=="04cc", ATTRS{idProduct}=="0802", MODE="0660", GROUP="dali"

# Hasseb DALI USB Master – USB-Zugriff (libusb/hidapi Fallback)
SUBSYSTEM=="usb", ATTR{idVendor}=="04cc", ATTR{idProduct}=="0802", MODE="0660", GROUP="dali"

# FTDI FT2232 (MikroE Click USB Adapter)
SUBSYSTEM=="usb", ATTR{idVendor}=="0403", ATTR{idProduct}=="6010", MODE="0660", GROUP="dali"
EOF
    info "udev-Regel installiert: ${UDEV_RULE_DALI}"

    # Alte Einzelregeln aufraeumen (falls vorhanden)
    rm -f /etc/udev/rules.d/99-hasseb-dali.rules
    rm -f /etc/udev/rules.d/99-hasseb-usb.rules
    rm -f /etc/udev/rules.d/99-ftdi-dali.rules

    udevadm control --reload-rules
    udevadm trigger
}

install_app() {
    info "Installiere Anwendung nach ${APP_DIR}..."

    # Verzeichnisse anlegen
    mkdir -p "${APP_DIR}"
    mkdir -p "${DATA_DIR}"

    # Konfigurationsdateien sichern (bei Update erhalten)
    local CONFIG_FILES=("driver_config.json" "labels.json" "devices.json" "dashboards.json")
    local BACKUP_DIR=""
    if [ -d "${DATA_DIR}" ] && [ "$(ls -A ${DATA_DIR}/*.json 2>/dev/null)" ]; then
        BACKUP_DIR="$(mktemp -d)"
        for cf in "${CONFIG_FILES[@]}"; do
            if [ -f "${DATA_DIR}/${cf}" ]; then
                cp "${DATA_DIR}/${cf}" "${BACKUP_DIR}/${cf}"
                info "Konfiguration gesichert: ${cf}"
            fi
        done
    fi

    # Quellcode kopieren (aus dem aktuellen Verzeichnis)
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    cp -r "${SCRIPT_DIR}/app" "${APP_DIR}/"
    cp "${SCRIPT_DIR}/requirements.txt" "${APP_DIR}/"

    # Konfigurationsdateien wiederherstellen
    if [ -n "${BACKUP_DIR}" ]; then
        for cf in "${CONFIG_FILES[@]}"; do
            if [ -f "${BACKUP_DIR}/${cf}" ]; then
                cp "${BACKUP_DIR}/${cf}" "${DATA_DIR}/${cf}"
                info "Konfiguration wiederhergestellt: ${cf}"
            fi
        done
        rm -rf "${BACKUP_DIR}"
    fi

    # Python Virtual Environment
    info "Erstelle Python venv und installiere Abhängigkeiten..."
    python3 -m venv "${VENV_DIR}"
    "${VENV_DIR}/bin/pip" install --upgrade pip -q
    "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt" -q

    # Berechtigungen setzen
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}"
    chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${DATA_DIR}"

    info "Anwendung installiert."
}

setup_systemd() {
    info "Richte systemd-Service ein..."
    cat > "${SYSTEMD_UNIT}" <<EOF
[Unit]
Description=DALI ServUI – DALI-Lichtsteuerung via Hasseb USB
After=network.target
Wants=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/gunicorn \\
    --bind 0.0.0.0:5000 \\
    --workers 1 \\
    --threads 4 \\
    --timeout 120 \\
    --access-logfile - \\
    app.main:create_app()

# Umgebungsvariablen
Environment=DALI_HOST=0.0.0.0
Environment=DALI_PORT=5000
Environment=DALI_DATA_DIR=${DATA_DIR}
Environment=DALI_LOG_LEVEL=INFO
Environment=DALI_LANG=de
Environment=PYTHONUNBUFFERED=1

# Sicherheit
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${DATA_DIR}
PrivateTmp=yes

# USB-Zugriff erlauben
SupplementaryGroups=plugdev

# Neustart bei Absturz
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${APP_NAME}"
    info "systemd-Service eingerichtet: ${APP_NAME}.service"
}

# ---------------------------------------------------------------------------
# Deinstallation
# ---------------------------------------------------------------------------
uninstall() {
    warn "Deinstalliere ${APP_NAME}..."

    # Service stoppen
    systemctl stop "${APP_NAME}" 2>/dev/null || true
    systemctl disable "${APP_NAME}" 2>/dev/null || true
    rm -f "${SYSTEMD_UNIT}"
    systemctl daemon-reload

    # Dateien entfernen
    rm -rf "${APP_DIR}"
    rm -f "${UDEV_RULE_DALI}"
    udevadm control --reload-rules

    # Benutzer und Daten bleiben erhalten (Sicherheit)
    warn "Daten-Verzeichnis ${DATA_DIR} wurde NICHT geloescht."
    warn "Benutzer '${SERVICE_USER}' wurde NICHT entfernt."
    info "Deinstallation abgeschlossen."
}

# ---------------------------------------------------------------------------
# Hauptprogramm
# ---------------------------------------------------------------------------
usage() {
    echo "Verwendung: $0 {install|uninstall|status}"
    echo ""
    echo "  install    – DALI ServUI installieren und Service einrichten"
    echo "  uninstall  – DALI ServUI deinstallieren (Daten bleiben erhalten)"
    echo "  status     – Status des Services anzeigen"
}

case "${1:-}" in
    install)
        check_root
        check_os
        install_packages
        create_user
        setup_udev
        install_app
        setup_systemd
        echo ""
        info "Installation abgeschlossen!"
        info "Service starten:  sudo systemctl start ${APP_NAME}"
        info "Web-UI oeffnen:   http://localhost:5000"
        info "Logs anzeigen:    sudo journalctl -u ${APP_NAME} -f"
        ;;
    uninstall)
        check_root
        uninstall
        ;;
    status)
        systemctl status "${APP_NAME}" 2>/dev/null || warn "Service nicht installiert."
        ;;
    *)
        usage
        exit 1
        ;;
esac
