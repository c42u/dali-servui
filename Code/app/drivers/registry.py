# =============================================================================
# DALI ServUI – Treiber-Registry
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Zentrale Registry für alle verfügbaren DALI-Treiber.
# Ermöglicht dynamische Auswahl über WebUI oder Konfiguration.
# =============================================================================

import logging
from typing import Optional

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliDriverInfo

logger = logging.getLogger(__name__)

# Registrierte Treiber-Klassen (lazy import um fehlende Dependencies zu tolerieren)
DRIVER_REGISTRY: dict[str, type] = {}


def _register_drivers():
    """Registriere alle verfügbaren Treiber.

    Jeder Treiber wird nur registriert, wenn sein Import funktioniert.
    So können optionale Dependencies (hidapi, gpiod, pyftdi) fehlen,
    ohne dass die Anwendung abstürzt.
    """
    # Dryrun ist immer verfügbar
    from app.drivers.dryrun import DryrunDriver
    DRIVER_REGISTRY['dryrun'] = DryrunDriver

    # Hasseb USB DALI Master (braucht hidapi)
    try:
        from app.drivers.hasseb import HassebHIDDriver
        DRIVER_REGISTRY['hasseb'] = HassebHIDDriver
    except ImportError:
        logger.debug("Hasseb-Treiber nicht verfügbar (hidapi fehlt)")

    # MikroE GPIO (braucht gpiod)
    try:
        from app.drivers.mikroe_gpio import MikroEGPIODriver
        DRIVER_REGISTRY['mikroe_gpio'] = MikroEGPIODriver
    except ImportError:
        logger.debug("MikroE GPIO-Treiber nicht verfügbar (gpiod fehlt)")

    # MikroE FTDI (braucht pyftdi)
    try:
        from app.drivers.mikroe_ftdi import MikroEFTDIDriver
        DRIVER_REGISTRY['mikroe_ftdi'] = MikroEFTDIDriver
    except ImportError:
        logger.debug("MikroE FTDI-Treiber nicht verfügbar (pyftdi fehlt)")


# Beim Import registrieren
_register_drivers()


def get_driver(driver_id: str, config: DaliDriverConfig) -> Optional[DaliDriver]:
    """Erstelle eine Treiber-Instanz anhand der ID.

    Args:
        driver_id: Treiber-ID (z.B. 'hasseb', 'mikroe_gpio', 'dryrun')
        config: Treiber-Konfiguration

    Returns:
        DaliDriver-Instanz oder None wenn der Treiber nicht verfügbar ist.
    """
    driver_class = DRIVER_REGISTRY.get(driver_id)
    if driver_class is None:
        logger.error("Unbekannter Treiber: %s", driver_id)
        return None

    config.driver_id = driver_id
    return driver_class(config)


def list_drivers() -> list[DaliDriverInfo]:
    """Liste alle registrierten Treiber mit ihren Informationen auf.

    Prüft für jeden Treiber, ob die Hardware verfügbar ist.

    Returns:
        Liste von DaliDriverInfo-Objekten
    """
    infos = []
    for driver_id, driver_class in DRIVER_REGISTRY.items():
        try:
            info = driver_class.get_info()
            infos.append(info)
        except Exception as e:
            logger.warning("Treiber-Info für '%s' fehlgeschlagen: %s",
                           driver_id, e)
    return infos
