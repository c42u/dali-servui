# =============================================================================
# DALI ServUI – Basis-Treiberklasse
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Abstrakte Basisklasse für alle DALI-Treiber. Jeder Treiber muss
# open(), close(), send_frame() und receive_frame() implementieren.
# =============================================================================

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class DaliDriverInfo:
    """Beschreibung eines verfügbaren Treibers für die WebUI."""
    id: str                             # Eindeutige ID (z.B. 'hasseb')
    name: str                           # Anzeigename (z.B. 'Hasseb USB DALI Master')
    description_de: str                 # Beschreibung Deutsch
    description_en: str                 # Beschreibung Englisch
    requires: list = field(default_factory=list)   # Benötigte Python-Pakete
    available: bool = False             # Ist die Hardware/Library verfügbar?
    config_fields: list = field(default_factory=list)  # Konfigurierbare Felder


@dataclass
class DaliDriverConfig:
    """Konfiguration für einen Treiber (aus WebUI oder ENV)."""
    # Allgemein
    driver_id: str = 'dryrun'

    # Hasseb
    hasseb_vendor: int = 0x04CC
    hasseb_product: int = 0x0802

    # MikroE GPIO (Raspberry Pi)
    gpio_tx_pin: int = 14              # BCM-Nummer: GPIO14 (RST auf Pi Click Shield)
    gpio_rx_pin: int = 15              # BCM-Nummer: GPIO15 (INT auf Pi Click Shield)
    gpio_tx_inverted: bool = False     # DALI Click: False, DALI 2 Click: True
    gpio_chip: str = '/dev/gpiochip0'  # gpiod Chip-Pfad

    # MikroE FTDI (Click USB Adapter)
    ftdi_url: str = 'ftdi://ftdi:2232h/1'  # pyftdi Device-URL
    ftdi_tx_pin: int = 4               # FTDI GPIO-Pin für TX (RST auf mikroBUS)
    ftdi_rx_pin: int = 7               # FTDI GPIO-Pin für RX (INT auf mikroBUS)
    ftdi_tx_inverted: bool = True      # DALI Click v1: True (OUT=1=idle), DALI 2 Click: prüfen
    ftdi_rx_inverted: bool = True      # RX-Logik invertiert (HIGH=idle bei DALI Click v1)

    # Feature-Flags (aktivierbar in Einstellungen)
    feature_dt6: bool = False          # DT6: LED Gear (Thermal, Current Limit)
    feature_dt8_tc: bool = False       # DT8: Tunable White (Farbtemperatur)
    feature_dt8_rgb: bool = False      # DT8: RGB/RGBWAF Farbsteuerung


@dataclass
class DaliFrame:
    """Ein DALI-Frame (Senden oder Empfangen)."""
    address: int = 0       # Byte A
    command: int = 0       # Byte B
    is_response: bool = False
    response_data: int = 0


class DaliDriver(ABC):
    """Abstrakte Basisklasse für DALI-Hardware-Treiber.

    Jeder Treiber muss die folgenden Methoden implementieren:
    - open():          Hardware öffnen und initialisieren
    - close():         Hardware schließen
    - send_frame():    DALI-Frame senden
    - receive_frame(): Auf DALI-Antwort warten
    - get_info():      Treiber-Informationen zurückgeben (classmethod)

    Optional:
    - read_firmware():  Firmware-Version lesen
    - enable_sniffing(): Bus-Monitoring aktivieren
    """

    def __init__(self, config: DaliDriverConfig):
        self._config = config
        self._is_open = False
        self.firmware_version = 'unknown'

    @property
    def is_open(self) -> bool:
        """Prüfe ob der Treiber geöffnet ist."""
        return self._is_open

    @classmethod
    @abstractmethod
    def get_info(cls) -> DaliDriverInfo:
        """Gib Treiber-Informationen zurück (für WebUI-Auswahl)."""
        ...

    @abstractmethod
    def open(self) -> bool:
        """Öffne die Hardware-Verbindung.

        Returns:
            True bei Erfolg, False bei Fehler.
        """
        ...

    @abstractmethod
    def close(self):
        """Schließe die Hardware-Verbindung."""
        ...

    @abstractmethod
    def send_frame(self, address: int, command: int,
                   expect_reply: bool = False,
                   send_twice: bool = False) -> Optional[DaliFrame]:
        """Sende einen DALI-Frame und warte optional auf Antwort.

        Args:
            address: DALI-Adresse (Byte A)
            command: DALI-Befehl (Byte B)
            expect_reply: True wenn eine Antwort erwartet wird
            send_twice: True für Config-Befehle (zweimal senden)

        Returns:
            DaliFrame mit Antwort oder None bei Fehler/Timeout.
        """
        ...

    def read_firmware(self) -> str:
        """Lese die Firmware-Version der Hardware (optional)."""
        return 'unknown'

    def enable_sniffing(self):
        """Aktiviere den Bus-Sniffer (optional)."""
        pass

    def disable_sniffing(self):
        """Deaktiviere den Bus-Sniffer (optional)."""
        pass

    def check_available(self) -> bool:
        """Prüfe ob die benötigte Hardware/Library verfügbar ist."""
        return True
