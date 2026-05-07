# =============================================================================
# DALI ServUI – Dryrun-Treiber (Testmodus)
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Simulierter Treiber für Tests ohne Hardware.
# Entspricht dem -n (dryrun) Modus des daliserver.
# =============================================================================

import logging
import time
from typing import Optional

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliDriverInfo, DaliFrame

logger = logging.getLogger(__name__)


class DryrunDriver(DaliDriver):
    """Simulierter DALI-Treiber für Tests ohne Hardware.

    Beantwortet alle Befehle mit simulierten Antworten:
    - Queries: Antwort 0xFF
    - Sonstige: Erfolg ohne Antwort
    - Simulierte Verzögerung von 10ms pro Befehl
    """

    @classmethod
    def get_info(cls) -> DaliDriverInfo:
        return DaliDriverInfo(
            id='dryrun',
            name='Testmodus (Dryrun)',
            description_de='Simulierter Treiber ohne echte Hardware. '
                           'Alle Befehle werden mit simulierten Antworten beantwortet. '
                           'Ideal zum Testen der Web-Oberfläche.',
            description_en='Simulated driver without real hardware. '
                           'All commands are answered with simulated responses. '
                           'Ideal for testing the web interface.',
            requires=[],
            available=True,  # Immer verfügbar
            config_fields=[]
        )

    def open(self) -> bool:
        """Immer erfolgreich."""
        self._is_open = True
        self.firmware_version = 'dryrun'
        logger.info("Dryrun-Treiber geöffnet")
        return True

    def close(self):
        """Nichts zu schließen."""
        self._is_open = False
        logger.info("Dryrun-Treiber geschlossen")

    def send_frame(self, address: int, command: int,
                   expect_reply: bool = False,
                   send_twice: bool = False) -> Optional[DaliFrame]:
        """Simuliere DALI-Kommunikation."""
        # Kurze Verzögerung simulieren
        time.sleep(0.010)

        logger.debug(
            "DRYRUN: addr=0x%02X cmd=0x%02X reply=%s twice=%s",
            address, command, expect_reply, send_twice
        )

        if expect_reply:
            return DaliFrame(is_response=True, response_data=0xFF)
        else:
            return DaliFrame(is_response=False)
