# =============================================================================
# DALI ServUI – Dockerfile
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Multi-Stage-Build: Abhaengigkeiten in Builder-Stage installieren,
# schlankes Runtime-Image mit USB-HID-Support.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Builder – Abhaengigkeiten kompilieren
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libhidapi-dev \
        libusb-1.0-0-dev \
        pkg-config && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY Code/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: Runtime – schlankes Image mit USB-Support
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Laufzeit-Abhaengigkeiten fuer USB-HID
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libhidapi-hidraw0 \
        libusb-1.0-0 \
        udev && \
    rm -rf /var/lib/apt/lists/*

# Nicht-Root-Benutzer anlegen
RUN groupadd -r dali && \
    useradd -r -g dali -d /app -s /sbin/nologin dali

# Python-Pakete aus Builder kopieren
COPY --from=builder /install /usr/local

# Anwendungscode kopieren
WORKDIR /app
COPY Code/app/ ./app/

# Daten-Verzeichnis (fuer Konfiguration, Backups)
RUN mkdir -p /app/data && chown -R dali:dali /app

# udev-Regel fuer Hasseb DALI USB Master
RUN echo 'KERNEL=="hidraw*", ATTRS{idVendor}=="04cc", ATTRS{idProduct}=="0802", MODE="0660", GROUP="dali"' \
    > /etc/udev/rules.d/99-hasseb-dali.rules

# Umgebungsvariablen
ENV DALI_HOST=0.0.0.0 \
    DALI_PORT=5000 \
    DALI_DATA_DIR=/app/data \
    DALI_LOG_LEVEL=INFO \
    DALI_LANG=de \
    PYTHONUNBUFFERED=1

# Port freigeben
EXPOSE 5000

# Healthcheck (auth-frei: /healthz statt /api/v1/status, damit DALI_API_TOKEN nicht stoert)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/healthz')" || exit 1

# Als dali-Benutzer ausfuehren
USER dali

# Gunicorn als WSGI-Server
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "1", \
     "--threads", "4", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "app.main:create_app()"]
