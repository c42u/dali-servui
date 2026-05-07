# =============================================================================
# DALI ServUI – Treiber-Paket
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Plugin-Treiber-Architektur für verschiedene DALI-Hardware:
# - hasseb:      Hasseb USB DALI Master (USB-HID)
# - mikroe_gpio: MikroE DALI Click / DALI 2 Click via GPIO (Raspberry Pi)
# - mikroe_ftdi: MikroE DALI Click / DALI 2 Click via Click USB Adapter (FTDI)
# - dryrun:      Testmodus ohne Hardware
# =============================================================================

from app.drivers.base import DaliDriver, DaliDriverInfo
from app.drivers.registry import get_driver, list_drivers, DRIVER_REGISTRY

__all__ = ['DaliDriver', 'DaliDriverInfo', 'get_driver', 'list_drivers']
