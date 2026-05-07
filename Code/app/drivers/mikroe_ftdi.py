# =============================================================================
# DALI ServUI – MikroE DALI Click FTDI-Treiber
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Treiber für MikroElektronika DALI Click / DALI 2 Click Boards,
# angeschlossen über den MikroE Click USB Adapter (FT2232H).
#
# Der Click USB Adapter verwendet einen FTDI FT2232H Chip, der die
# mikroBUS-Pins (inkl. RST=TX und INT=RX) über USB bereitstellt.
#
# Hardware-Zuordnung Click USB Adapter:
#   FT2232H Channel A:
#   - ADBUS4 → RST (mikroBUS) → DALI TX
#   - ADBUS7 → INT (mikroBUS) → DALI RX
#
# DALI-Protokoll: Manchester-Encoding bei 1200 Baud (416.7 µs Halbbit)
#
# WICHTIG: Einzelne GPIO-Writes über USB dauern ~1ms (USB-Roundtrip).
# DALI braucht 416.7 µs pro Halbbit – zu schnell für einzelne Writes.
# Loesung: Async Bitbang Mode mit gepuffertem Waveform-Buffer.
# Der FTDI-Chip taktet die Pin-Zustände selbständig mit der
# eingestellten Baudrate aus, unabhängig vom USB-Timing.
#
# Für den Empfang (RX) wird nach dem Senden ein Leseblock gelesen
# und die Manchester-decodierten Bits daraus extrahiert.
# =============================================================================

import logging
import time
from typing import Optional

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliDriverInfo, DaliFrame

logger = logging.getLogger(__name__)

# DALI-Timing
DALI_HALF_BIT_US = 416.7
DALI_FULL_BIT_US = 833.3
DALI_SETTLE_US = 2400.0

# Bitbang-Samplerate: Samples pro Sekunde
# WICHTIG: FTDI Async Bitbang taktet mit baudrate × 16!
# Daher: gewünschte Sample-Rate / 16 = Baudrate für set_baudrate().
#
# Ziel: 9600 Samples/s → set_baudrate(600) → 600 × 16 = 9600 eff. Hz
# Jedes Sample = ein Byte das den Pin-Zustand beschreibt.
# 4 Samples pro Halbbit × 104.2 µs/Sample = 416.7 µs = DALI-Halbbit
BITBANG_SAMPLE_RATE = 9600          # Effektive Sample-Rate (Hz)
BITBANG_BAUDRATE = 9600 // 16       # 600 – an set_baudrate() übergeben
SAMPLES_PER_HALFBIT = 4             # 4 × 104.2 µs = 416.7 µs


class MikroEFTDIDriver(DaliDriver):
    """Treiber für MikroE DALI Click via Click USB Adapter (FTDI FT2232H).

    Nutzt den FTDI Async Bitbang Mode für präzises DALI-Timing:
    - TX: Gesamte Manchester-Wellenform wird als Byte-Buffer vorberechnet
      und per USB-Bulk-Transfer auf einmal gesendet. Der FTDI-Chip
      taktet die Pin-Zustände mit BITBANG_SAMPLE_RATE aus.
    - RX: Nach dem Senden wird ein Block von Samples gelesen.
      Die empfangenen Pin-Zustände werden Manchester-decodiert.
    """

    def __init__(self, config: DaliDriverConfig):
        super().__init__(config)
        self._ftdi = None
        self._tx_mask = 0
        self._rx_mask = 0
        self._idle_byte = 0

    @classmethod
    def get_info(cls) -> DaliDriverInfo:
        """Treiber-Informationen für die WebUI."""
        available = False
        try:
            from pyftdi.ftdi import Ftdi
            devices = Ftdi.list_devices()
            available = len(devices) > 0
        except (ImportError, Exception):
            pass

        return DaliDriverInfo(
            id='mikroe_ftdi',
            name='MikroE DALI Click (USB Adapter)',
            description_de='MikroElektronika DALI Click oder DALI 2 Click Board, '
                           'angeschlossen über den Click USB Adapter (FT2232H). '
                           'Funktioniert an jedem PC mit USB.',
            description_en='MikroElektronika DALI Click or DALI 2 Click board, '
                           'connected via Click USB Adapter (FT2232H). '
                           'Works on any PC with USB.',
            requires=['pyftdi'],
            available=available,
            config_fields=[
                {'id': 'ftdi_url', 'label_de': 'FTDI Device-URL',
                 'label_en': 'FTDI Device URL', 'type': 'text',
                 'default': 'ftdi://ftdi:2232h/1'},
                {'id': 'ftdi_tx_pin', 'label_de': 'TX GPIO-Pin (FTDI)',
                 'label_en': 'TX GPIO Pin (FTDI)', 'type': 'number',
                 'default': 4, 'min': 0, 'max': 7},
                {'id': 'ftdi_rx_pin', 'label_de': 'RX GPIO-Pin (FTDI)',
                 'label_en': 'RX GPIO Pin (FTDI)', 'type': 'number',
                 'default': 7, 'min': 0, 'max': 7},
                {'id': 'ftdi_tx_inverted',
                 'label_de': 'TX invertiert (DALI Click v1: an)',
                 'label_en': 'TX inverted (DALI Click v1: on)',
                 'type': 'checkbox', 'default': True},
                {'id': 'ftdi_rx_inverted',
                 'label_de': 'RX invertiert (DALI Click v1: an)',
                 'label_en': 'RX inverted (DALI Click v1: on)',
                 'type': 'checkbox', 'default': True},
            ]
        )

    def check_available(self) -> bool:
        """Prüfe ob ein FTDI-Gerät vorhanden ist."""
        try:
            from pyftdi.ftdi import Ftdi
            devices = Ftdi.list_devices()
            return len(devices) > 0
        except (ImportError, Exception):
            return False

    def open(self) -> bool:
        """Öffne den FTDI im Async Bitbang Mode."""
        try:
            from pyftdi.ftdi import Ftdi

            self._tx_mask = 1 << self._config.ftdi_tx_pin
            self._rx_mask = 1 << self._config.ftdi_rx_pin

            # Idle-Byte: TX-Pin im Ruhezustand
            if self._config.ftdi_tx_inverted:
                self._idle_byte = self._tx_mask  # invertiert: HIGH = idle
            else:
                self._idle_byte = 0              # normal: LOW = idle

            self._ftdi = Ftdi()
            self._ftdi.open_from_url(self._config.ftdi_url)

            # Async Bitbang Mode: direction = TX-Pin als Output
            self._ftdi.set_bitmode(self._tx_mask, Ftdi.BitMode.BITBANG)
            self._ftdi.set_baudrate(BITBANG_BAUDRATE)

            # Latenz-Timer minimieren (1ms = kleinstmöglicher Wert)
            self._ftdi.set_latency_timer(1)

            # TX in Ruhezustand setzen
            self._ftdi.write_data(bytes([self._idle_byte]))

            self._is_open = True
            self.firmware_version = 'FTDI-BB'
            logger.info(
                "MikroE FTDI-Treiber (Bitbang) geöffnet: URL=%s, "
                "TX=Pin%d (inv=%s), RX=Pin%d (inv=%s), Rate=%d Hz (baud=%d)",
                self._config.ftdi_url,
                self._config.ftdi_tx_pin, self._config.ftdi_tx_inverted,
                self._config.ftdi_rx_pin, self._config.ftdi_rx_inverted,
                BITBANG_SAMPLE_RATE, BITBANG_BAUDRATE
            )
            return True

        except ImportError:
            logger.error("Python-Paket 'pyftdi' nicht installiert")
            return False
        except Exception as e:
            logger.error("FTDI konnte nicht geöffnet werden: %s", e)
            self._ftdi = None
            return False

    def close(self):
        """Schließe den FTDI-Zugang."""
        if self._ftdi:
            try:
                # Zurück in Reset-Mode
                self._ftdi.set_bitmode(0, Ftdi.BitMode.RESET)
                self._ftdi.close()
            except Exception:
                pass
            self._ftdi = None
        self._is_open = False

    def send_frame(self, address: int, command: int,
                   expect_reply: bool = False,
                   send_twice: bool = False) -> Optional[DaliFrame]:
        """Sende einen DALI Forward Frame via FTDI Bitbang."""
        if not self._ftdi:
            return None

        # Forward Frame: 16 Bit
        frame_data = ((address & 0xFF) << 8) | (command & 0xFF)

        # Waveform als Byte-Buffer vorberechnen
        waveform = self._build_forward_waveform(frame_data)

        if send_twice:
            # 10ms Pause zwischen den Frames (= ~96 Idle-Samples bei 9600 Hz)
            gap = bytes([self._idle_byte]) * 96
            waveform = waveform + gap + self._build_forward_waveform(frame_data)

        # RX-Buffer leeren vor dem Senden
        self._ftdi.purge_rx_buffer()

        # Gesamte Waveform auf einmal senden
        self._ftdi.write_data(waveform)

        if not expect_reply:
            # Kurz warten bis der FTDI-Chip fertig ist
            tx_duration = len(waveform) / BITBANG_SAMPLE_RATE
            time.sleep(tx_duration + 0.002)
            return DaliFrame(is_response=False)

        # Settling Time + Antwortfenster abwarten
        # Forward Frame Dauer + Settle + Backward Frame
        tx_duration = len(waveform) / BITBANG_SAMPLE_RATE
        settle_s = DALI_SETTLE_US / 1_000_000
        # Backward Frame: 1 Start + 8 Daten + 2 Stop = ~11 Bits × 833µs = ~9.2ms
        backward_window = 22 * DALI_FULL_BIT_US / 1_000_000
        total_wait = tx_duration + settle_s + backward_window
        time.sleep(total_wait + 0.005)

        # RX-Samples lesen
        response = self._read_backward_frame()

        if response is not None:
            return DaliFrame(is_response=True, response_data=response)
        return DaliFrame(is_response=False)

    # -------------------------------------------------------------------
    # TX: Manchester-Waveform vorberechnen
    # -------------------------------------------------------------------
    def _build_forward_waveform(self, data: int) -> bytes:
        """Baue die gesamte Manchester-Wellenform als Byte-Buffer.

        Jedes Byte im Buffer = ein Pin-Zustand, getaktet mit BITBANG_SAMPLE_RATE.
        SAMPLES_PER_HALFBIT Bytes pro Halbbit.

        Manchester-Encoding (DALI):
        - Bit 1: erste Hälfte HIGH, zweite Hälfte LOW (Bus: LOW→HIGH)
        - Bit 0: erste Hälfte LOW, zweite Hälfte HIGH (Bus: HIGH→LOW)
        """
        inv = self._config.ftdi_tx_inverted
        tx_high = self._tx_mask if not inv else 0
        tx_low = 0 if not inv else self._tx_mask
        n = SAMPLES_PER_HALFBIT
        buf = bytearray()

        # Startbit (immer 1): HIGH-LOW
        buf.extend([tx_high] * n)
        buf.extend([tx_low] * n)

        # 16 Datenbits (MSB first)
        for i in range(15, -1, -1):
            bit = (data >> i) & 1
            if bit == 1:
                buf.extend([tx_high] * n)
                buf.extend([tx_low] * n)
            else:
                buf.extend([tx_low] * n)
                buf.extend([tx_high] * n)

        # 2 Stopbits (Idle)
        buf.extend([self._idle_byte] * (n * 4))

        return bytes(buf)

    # -------------------------------------------------------------------
    # RX: Backward Frame aus Bitbang-Samples decodieren
    # -------------------------------------------------------------------
    def _read_backward_frame(self) -> Optional[int]:
        """Lese und decodiere einen 8-Bit Backward Frame aus RX-Samples.

        Im Async Bitbang Mode liest der FTDI-Chip die Pin-Zustände
        mit BITBANG_SAMPLE_RATE und puffert sie intern. Wir lesen den gesamten
        Buffer und suchen darin nach dem Backward Frame.
        """
        try:
            # Alle verfügbaren Samples lesen
            rx_data = self._ftdi.read_data(4096)
        except Exception as e:
            logger.error("FTDI RX Lesefehler: %s", e)
            return None

        if not rx_data or len(rx_data) < SAMPLES_PER_HALFBIT * 2:
            return None

        # Pin-Zustände in Bitfolge umwandeln
        inv = self._config.ftdi_rx_inverted
        bits = []
        for byte_val in rx_data:
            raw = 1 if (byte_val & self._rx_mask) else 0
            bits.append(1 - raw if inv else raw)

        # Startbit suchen: Übergang von 0 auf 1 (nach Idle=0)
        start_idx = None
        for i in range(len(bits) - 1):
            if bits[i] == 0 and bits[i + 1] == 1:
                start_idx = i + 1
                break

        if start_idx is None:
            return None

        # Ab Startbit: Samples in Bitperioden einteilen
        # Abtastpunkt: Mitte jeder Bitperiode (3/4 der ersten Halbbit-Dauer)
        samples_per_bit = SAMPLES_PER_HALFBIT * 2
        sample_offset = start_idx + int(SAMPLES_PER_HALFBIT * 0.75)

        # Startbit verifizieren (sollte 1 sein)
        if sample_offset >= len(bits):
            return None
        if bits[sample_offset] != 1:
            return None

        # 8 Datenbits lesen (MSB first)
        data = 0
        for bit_num in range(8):
            idx = sample_offset + (bit_num + 1) * samples_per_bit
            if idx >= len(bits):
                logger.debug("RX: Nicht genug Samples für Bit %d", bit_num)
                return None
            bit_val = bits[idx]
            data = (data << 1) | bit_val

        logger.debug("RX Backward Frame: 0x%02X (%d Samples gelesen)",
                     data, len(rx_data))
        return data

    @staticmethod
    def _precise_delay(seconds: float):
        """Präzise Verzögerung per Busy-Wait (für Settle-Zeiten)."""
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            pass
