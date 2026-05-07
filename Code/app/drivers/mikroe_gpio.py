# =============================================================================
# DALI ServUI – MikroE DALI Click GPIO-Treiber
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# GPIO-basierter Treiber für MikroElektronika DALI Click und DALI 2 Click
# Boards, angeschlossen über Pi Click Shield an einen Raspberry Pi.
#
# Hardware-Anschluss:
#   Pi Click Shield → DALI Click/DALI 2 Click
#   GPIO14 (BCM) → RST (mikroBUS) → DALI TX
#   GPIO15 (BCM) → INT (mikroBUS) → DALI RX
#
# DALI-Protokoll:
#   - Manchester-Encoding, 1200 Baud (Halbbit-Zeit: 416.7µs)
#   - Forward Frame: 1 Startbit + 16 Datenbits = 17 Bits
#   - Backward Frame: 1 Startbit + 8 Datenbits = 9 Bits
#
# WICHTIG: DALI Click und DALI 2 Click haben invertierte TX-Logik!
#   - DALI Click:   TX HIGH = Bus inaktiv (nicht invertiert)
#   - DALI 2 Click: TX HIGH = Bus aktiv   (invertiert)
#   → Konfigurierbar über gpio_tx_inverted
# =============================================================================

import logging
import time
from typing import Optional

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliDriverInfo, DaliFrame

logger = logging.getLogger(__name__)

# DALI-Timing-Konstanten
DALI_HALF_BIT_US = 416.7    # Halbbit-Zeit in Mikrosekunden
DALI_FULL_BIT_US = 833.3    # Vollbit-Zeit in Mikrosekunden
DALI_SETTLE_US = 2400.0     # Settling Time zwischen Forward und Backward Frame
DALI_RESPONSE_TIMEOUT_MS = 22 * DALI_FULL_BIT_US / 1000  # ~18.3ms


class MikroEGPIODriver(DaliDriver):
    """Treiber für MikroE DALI Click / DALI 2 Click via Raspberry Pi GPIO.

    Verwendet gpiod (libgpiod) für den GPIO-Zugriff – das ist die moderne,
    kernel-unabhängige Methode (RPi.GPIO ist deprecated seit Kernel 6.x).

    Das DALI-Protokoll wird per Software-Bit-Banging implementiert:
    Manchester-Encoding mit 416.7µs Halbbit-Timing.
    """

    def __init__(self, config: DaliDriverConfig):
        super().__init__(config)
        self._chip = None
        self._tx_line = None
        self._rx_line = None

    @classmethod
    def get_info(cls) -> DaliDriverInfo:
        """Treiber-Informationen für die WebUI."""
        available = False
        try:
            import gpiod
            available = True
        except ImportError:
            pass

        return DaliDriverInfo(
            id='mikroe_gpio',
            name='MikroE DALI Click (GPIO)',
            description_de='MikroElektronika DALI Click oder DALI 2 Click Board, '
                           'angeschlossen über Pi Click Shield an Raspberry Pi GPIO. '
                           'TX=GPIO14, RX=GPIO15 (konfigurierbar).',
            description_en='MikroElektronika DALI Click or DALI 2 Click board, '
                           'connected via Pi Click Shield to Raspberry Pi GPIO. '
                           'TX=GPIO14, RX=GPIO15 (configurable).',
            requires=['gpiod'],
            available=available,
            config_fields=[
                {'id': 'gpio_tx_pin', 'label_de': 'TX GPIO-Pin (BCM)',
                 'label_en': 'TX GPIO Pin (BCM)', 'type': 'number',
                 'default': 14, 'min': 0, 'max': 27},
                {'id': 'gpio_rx_pin', 'label_de': 'RX GPIO-Pin (BCM)',
                 'label_en': 'RX GPIO Pin (BCM)', 'type': 'number',
                 'default': 15, 'min': 0, 'max': 27},
                {'id': 'gpio_tx_inverted', 'label_de': 'TX invertiert (DALI 2 Click)',
                 'label_en': 'TX inverted (DALI 2 Click)', 'type': 'checkbox',
                 'default': False},
                {'id': 'gpio_chip', 'label_de': 'GPIO-Chip',
                 'label_en': 'GPIO Chip', 'type': 'text',
                 'default': '/dev/gpiochip0'},
            ]
        )

    def check_available(self) -> bool:
        """Prüfe ob gpiod und der GPIO-Chip verfügbar sind."""
        try:
            import gpiod
            chip = gpiod.Chip(self._config.gpio_chip)
            chip.close()
            return True
        except Exception:
            return False

    def open(self) -> bool:
        """Öffne die GPIO-Verbindung."""
        try:
            import gpiod

            self._chip = gpiod.Chip(self._config.gpio_chip)

            # TX-Pin als Output konfigurieren
            self._tx_line = self._chip.get_line(self._config.gpio_tx_pin)
            # Startwert: Bus inaktiv
            initial_tx = 0 if not self._config.gpio_tx_inverted else 1
            self._tx_line.request(
                consumer='dali-servui-tx',
                type=gpiod.LINE_REQ_DIR_OUT,
                default_val=initial_tx
            )

            # RX-Pin als Input konfigurieren
            self._rx_line = self._chip.get_line(self._config.gpio_rx_pin)
            self._rx_line.request(
                consumer='dali-servui-rx',
                type=gpiod.LINE_REQ_DIR_IN
            )

            self._is_open = True
            self.firmware_version = 'GPIO'
            logger.info(
                "MikroE GPIO-Treiber geöffnet (TX=GPIO%d, RX=GPIO%d, inv=%s)",
                self._config.gpio_tx_pin, self._config.gpio_rx_pin,
                self._config.gpio_tx_inverted
            )
            return True

        except ImportError:
            logger.error("Python-Paket 'gpiod' nicht installiert")
            return False
        except Exception as e:
            logger.error("GPIO konnte nicht geöffnet werden: %s", e)
            self._cleanup_gpio()
            return False

    def close(self):
        """Schließe die GPIO-Verbindung."""
        self._cleanup_gpio()
        self._is_open = False

    def _cleanup_gpio(self):
        """GPIO-Ressourcen freigeben."""
        if self._tx_line:
            try:
                self._tx_line.release()
            except Exception:
                pass
            self._tx_line = None
        if self._rx_line:
            try:
                self._rx_line.release()
            except Exception:
                pass
            self._rx_line = None
        if self._chip:
            try:
                self._chip.close()
            except Exception:
                pass
            self._chip = None

    def send_frame(self, address: int, command: int,
                   expect_reply: bool = False,
                   send_twice: bool = False) -> Optional[DaliFrame]:
        """Sende einen DALI Forward Frame via Manchester-Encoding."""
        if not self._tx_line or not self._rx_line:
            return None

        # Forward Frame zusammenbauen: 16 Bit (address + command)
        frame_data = ((address & 0xFF) << 8) | (command & 0xFF)

        # Frame senden
        self._send_manchester_forward(frame_data)

        # Bei Doppelsendung: 10ms warten und nochmal senden
        if send_twice:
            time.sleep(0.010)
            self._send_manchester_forward(frame_data)

        if not expect_reply:
            return DaliFrame(is_response=False)

        # Auf Backward Frame warten (Settling Time + Antwort)
        time.sleep(DALI_SETTLE_US / 1_000_000)
        response = self._receive_manchester_backward()

        if response is not None:
            return DaliFrame(is_response=True, response_data=response)
        else:
            return DaliFrame(is_response=False)

    def _send_manchester_forward(self, data: int):
        """Sende einen 16-Bit DALI Forward Frame mit Manchester-Encoding.

        Manchester-Encoding:
        - Logisch 1: HIGH in erster Halbbitzeit, LOW in zweiter
        - Logisch 0: LOW in erster Halbbitzeit, HIGH in zweiter
        - Startbit: Immer 1

        Bei invertiertem TX (DALI 2 Click) werden die Pegel vertauscht.
        """
        inv = self._config.gpio_tx_inverted
        half_bit = DALI_HALF_BIT_US / 1_000_000  # In Sekunden

        # Startbit senden (immer 1)
        self._manchester_bit(1, half_bit, inv)

        # 16 Datenbits senden (MSB first)
        for i in range(15, -1, -1):
            bit = (data >> i) & 1
            self._manchester_bit(bit, half_bit, inv)

        # Bus wieder in Ruhezustand
        self._set_tx(0 if not inv else 1)

    def _manchester_bit(self, bit: int, half_bit: float, inverted: bool):
        """Sende ein einzelnes Manchester-codiertes Bit."""
        if bit == 1:
            # Logisch 1: HIGH → LOW
            self._set_tx(1 if not inverted else 0)
            self._precise_delay(half_bit)
            self._set_tx(0 if not inverted else 1)
            self._precise_delay(half_bit)
        else:
            # Logisch 0: LOW → HIGH
            self._set_tx(0 if not inverted else 1)
            self._precise_delay(half_bit)
            self._set_tx(1 if not inverted else 0)
            self._precise_delay(half_bit)

    def _receive_manchester_backward(self) -> Optional[int]:
        """Empfange einen 8-Bit DALI Backward Frame.

        Wartet auf das Startbit und liest dann 8 Datenbits.
        Timeout: ~22 Vollbit-Zeiten.

        Returns:
            Antwort-Byte (0..255) oder None bei Timeout.
        """
        half_bit = DALI_HALF_BIT_US / 1_000_000
        timeout = 22 * DALI_FULL_BIT_US / 1_000_000

        # Auf Startbit warten (Flanke HIGH)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._get_rx() == 1:
                break
        else:
            return None  # Timeout – keine Antwort

        # Mitte des Startbits abwarten
        self._precise_delay(half_bit * 1.5)

        # 8 Datenbits lesen (MSB first)
        data = 0
        for i in range(7, -1, -1):
            # Sample in der Mitte der ersten Halbbit-Zeit
            bit = self._get_rx()
            data |= (bit << i)
            # Zur nächsten Bit-Mitte springen
            self._precise_delay(half_bit * 2)

        return data

    def _set_tx(self, value: int):
        """Setze den TX-Pin."""
        try:
            self._tx_line.set_value(value)
        except Exception as e:
            logger.error("GPIO TX set_value Fehler: %s", e)

    def _get_rx(self) -> int:
        """Lese den RX-Pin."""
        try:
            return self._rx_line.get_value()
        except Exception as e:
            logger.error("GPIO RX get_value Fehler: %s", e)
            return 0

    @staticmethod
    def _precise_delay(seconds: float):
        """Präzise Verzögerung per Busy-Wait.

        time.sleep() ist auf Linux nicht präzise genug für das
        DALI-Timing (~416µs). Busy-Wait ist CPU-intensiv, aber
        für die kurzen DALI-Frames akzeptabel.
        """
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            pass
