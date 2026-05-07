# =============================================================================
# DALI ServUI – Konfiguration
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# =============================================================================

import logging
import os
import secrets

logger = logging.getLogger(__name__)

# Basis-Verzeichnis der Anwendung
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Daten-Verzeichnis (Konfiguration, Backup)
DATA_DIR = os.environ.get('DALI_DATA_DIR', os.path.join(BASE_DIR, '..', 'data'))


def _resolve_secret_key() -> str:
    """SECRET_KEY-Auflösung in dieser Reihenfolge:
    1. ENV DALI_SECRET_KEY (falls gesetzt und nicht der Bootstrap-Default)
    2. persistent in DATA_DIR/secret_key (wird beim ersten Start angelegt)
    """
    env_value = os.environ.get('DALI_SECRET_KEY', '').strip()
    if env_value and env_value != 'change-me-in-production':
        return env_value

    if env_value == 'change-me-in-production':
        logger.warning(
            "DALI_SECRET_KEY hat den Bootstrap-Default 'change-me-in-production' – "
            "verwende stattdessen den persistierten Schlüssel.")

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except OSError:
        # DATA_DIR nicht beschreibbar (z.B. Tests) → Random-Key (nicht persistent)
        return secrets.token_urlsafe(48)

    key_file = os.path.join(DATA_DIR, 'secret_key')
    if os.path.exists(key_file):
        with open(key_file, 'r', encoding='utf-8') as f:
            data = f.read().strip()
        if data:
            return data

    new_key = secrets.token_urlsafe(48)
    try:
        with open(key_file, 'w', encoding='utf-8') as f:
            f.write(new_key)
        os.chmod(key_file, 0o600)
        logger.info("Neuen SECRET_KEY in %s erzeugt (0600)", key_file)
    except OSError as exc:
        logger.warning("Konnte SECRET_KEY nicht persistieren: %s", exc)
    return new_key


# Flask-Konfiguration
SECRET_KEY = _resolve_secret_key()
DEBUG = os.environ.get('DALI_DEBUG', 'false').lower() == 'true'

# DALI-Treiber (hasseb, mikroe_gpio, mikroe_ftdi, dryrun)
# Leer = aus gespeicherter Konfiguration laden, sonst Fallback auf dryrun
DALI_DRIVER = os.environ.get('DALI_DRIVER', '')

# Web-Server
HOST = os.environ.get('DALI_HOST', '0.0.0.0')
PORT = int(os.environ.get('DALI_PORT', '5000'))

# Sprache (de/en)
DEFAULT_LANGUAGE = os.environ.get('DALI_LANG', 'de')

# API-Token (optional, leer = kein Auth)
API_TOKEN = os.environ.get('DALI_API_TOKEN', '')

# CORS-Origins (Komma-separierte Liste, "*" für alle, leer = keine CORS-Header)
# Beispiele: "https://homeassistant.local:8123,http://localhost:8123"
_cors_raw = os.environ.get('DALI_CORS_ORIGINS', '').strip()
CORS_ORIGINS: list[str] = (
    [o.strip() for o in _cors_raw.split(',') if o.strip()]
    if _cors_raw else []
)

# Logging
LOG_LEVEL = os.environ.get('DALI_LOG_LEVEL', 'INFO')
LOG_FILE = os.environ.get('DALI_LOG_FILE', '')

# Version
VERSION = '1.0.0'
