# =============================================================================
# DALI ServUI – Hasseb USB DALI Master Treiber
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# USB-HID-Treiber für den Hasseb DALI USB Master.
# Hardware: Vendor 0x04CC, Product 0x0802
# Protokoll: 10-Byte HID-Pakete mit Sequenznummern
# =============================================================================

import logging
import struct
import time
from enum import IntEnum
from typing import Optional

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliDriverInfo, DaliFrame

logger = logging.getLogger(__name__)

# Hasseb HID-Konstanten
HASSEB_USB_VENDOR = 0x04CC
HASSEB_USB_PRODUCT = 0x0802
HASSEB_PACKET_HEADER = 0xAA
HASSEB_READ_FIRMWARE_VERSION = 0x02
HASSEB_CONFIGURE_DEVICE = 0x05
HASSEB_DALI_FRAME = 0x07


class HassebStatus(IntEnum):
    """Antwort-Status vom Hasseb-Adapter."""
    NO_DATA_AVAILABLE = 0
    NO_ANSWER = 1
    OK = 2
    INVALID_ANSWER = 3
    ANSWER_TOO_EARLY = 4
    SNIFFER_BYTE = 5
    SNIFFER_BYTE_ERROR = 6


class HassebHIDDriver(DaliDriver):
    """Treiber für den Hasseb USB DALI Master (USB-HID).

    Kommuniziert über hidapi mit dem Hasseb-Adapter.
    Paketformat: 10 Bytes (Header, CMD, SeqNo, FrameLen,
    ExpectReply, SettleTime, SendTwice, ByteA, ByteB, Pad).
    """

    def __init__(self, config: DaliDriverConfig):
        super().__init__(config)
        self._device = None
        self._seqnum = 0
        self._sniffer_callback = None
        self._sniffing = False

    @classmethod
    def get_info(cls) -> DaliDriverInfo:
        """Treiber-Informationen für die WebUI."""
        # Prüfe ob hidapi verfügbar ist
        available = False
        try:
            import hid
            devices = hid.enumerate(HASSEB_USB_VENDOR, HASSEB_USB_PRODUCT)
            available = len(devices) > 0
        except ImportError:
            pass

        return DaliDriverInfo(
            id='hasseb',
            name='Hasseb USB DALI Master',
            description_de='USB-HID DALI-Controller mit integrierter Bus-Stromversorgung (250mA). '
                           'Plug & Play an jedem PC mit USB.',
            description_en='USB-HID DALI controller with integrated bus power supply (250mA). '
                           'Plug & play on any PC with USB.',
            requires=['hidapi'],
            available=available,
            config_fields=[]  # Keine extra Konfiguration nötig
        )

    def check_available(self) -> bool:
        """Prüfe ob ein Hasseb-Gerät angeschlossen ist."""
        try:
            import hid
            devices = hid.enumerate(HASSEB_USB_VENDOR, HASSEB_USB_PRODUCT)
            return len(devices) > 0
        except ImportError:
            return False

    def open(self) -> bool:
        """Öffne das Hasseb USB-Gerät."""
        try:
            import hid
            self._device = hid.device()
            self._device.open(
                self._config.hasseb_vendor,
                self._config.hasseb_product
            )
            self._device.set_nonblocking(1)
            self._is_open = True

            # Firmware-Version lesen
            self.firmware_version = self.read_firmware()
            logger.info(
                "Hasseb DALI USB Master geöffnet (Firmware: %s)",
                self.firmware_version
            )
            return True

        except ImportError:
            logger.error("Python-Paket 'hidapi' nicht installiert")
            return False
        except Exception as e:
            logger.error("Hasseb USB konnte nicht geöffnet werden: %s", e)
            self._device = None
            return False

    def close(self):
        """Schließe das USB-Gerät."""
        if self._device:
            try:
                self._device.close()
            except Exception:
                pass
            self._device = None
        self._is_open = False

    def _next_seqnum(self) -> int:
        """Nächste Sequenznummer (1..255, Wraparound)."""
        self._seqnum = (self._seqnum % 255) + 1
        return self._seqnum

    def send_frame(self, address: int, command: int,
                   expect_reply: bool = False,
                   send_twice: bool = False) -> Optional[DaliFrame]:
        """Sende einen DALI-Frame über USB-HID."""
        if not self._device:
            return None

        seqnum = self._next_seqnum()

        # Settling Time: Hasseb-Firmware Wert (Vielfache von ~10ms)
        # Bei send_twice: 10 = ~100ms zwischen den Frames
        settle = 10 if send_twice else 0

        # HID-Paket konstruieren
        data = struct.pack(
            'BBBBBBBBBB',
            HASSEB_PACKET_HEADER,
            HASSEB_DALI_FRAME,
            seqnum,
            16,  # Frame-Länge
            1 if expect_reply else 0,
            settle,
            10 if send_twice else 0,
            address & 0xFF,
            command & 0xFF,
            0    # Padding
        )

        # Buffer leeren vor expect_reply-Frames (verhindert Stale-Data)
        if expect_reply:
            self._flush_hid_buffer()

        # Inter-Frame-Delay
        if send_twice:
            time.sleep(0.050)
        else:
            time.sleep(0.030)

        # Senden mit Retry bei Fehler
        for attempt in range(2):
            try:
                self._device.write(data)
                logger.debug(
                    "HID TX: seq=%d addr=0x%02X cmd=0x%02X reply=%s twice=%s",
                    seqnum, address, command, expect_reply, send_twice
                )
                break
            except Exception as e:
                logger.error("HID-Sendefehler (Versuch %d): %s", attempt + 1, e)
                if attempt == 0:
                    self._try_reconnect()
                    if not self._device:
                        return None
                    time.sleep(0.1)
                else:
                    return None

        # Auf Antwort warten (send_twice braucht längeren Timeout)
        extra_timeout = 0.5 if send_twice else 0.0
        return self._wait_response(expect_reply, extra_timeout)

    def _flush_hid_buffer(self):
        """Lese alle anstehenden HID-Daten um den Buffer zu leeren."""
        if not self._device:
            return
        try:
            for _ in range(50):
                data = self._device.read(10)
                if not data:
                    break
        except Exception:
            pass

    def _try_reconnect(self):
        """Versuche den Hasseb nach einem Fehler neu zu öffnen."""
        logger.warning("Versuche Hasseb USB Reconnect...")
        try:
            if self._device:
                try:
                    self._device.close()
                except Exception:
                    pass
            import hid
            self._device = hid.device()
            self._device.open(
                self._config.hasseb_vendor,
                self._config.hasseb_product
            )
            self._device.set_nonblocking(1)
            logger.info("Hasseb USB Reconnect erfolgreich")
        except Exception as e:
            logger.error("Hasseb USB Reconnect fehlgeschlagen: %s", e)
            self._device = None
            self._is_open = False

    def _wait_response(self, expect_reply: bool,
                       extra_timeout: float = 0.0) -> Optional[DaliFrame]:
        """Warte auf Antwort vom Hasseb-Adapter."""
        timeout = (1.0 if expect_reply else 0.5) + extra_timeout
        deadline = time.time() + timeout

        while time.time() < deadline:
            try:
                data = self._device.read(10)
            except Exception as e:
                logger.error("HID-Lesefehler: %s", e)
                return None

            if not data or len(data) < 6:
                time.sleep(0.005)
                continue

            # No-Data überspringen
            if data[1] == HassebStatus.NO_DATA_AVAILABLE:
                time.sleep(0.005)
                continue

            if data[1] == HASSEB_DALI_FRAME:
                status = data[3]

                # Sniffer-Bytes an den Sniffer-Callback weiterleiten
                if status in (HassebStatus.SNIFFER_BYTE,
                              HassebStatus.SNIFFER_BYTE_ERROR):
                    if self._sniffer_callback:
                        sniffer_byte = data[5] if len(data) > 5 else 0
                        is_error = (status == HassebStatus.SNIFFER_BYTE_ERROR)
                        self._sniffer_callback(sniffer_byte, is_error)
                    continue

                if status == HassebStatus.OK and data[4] == 1:
                    # Antwort mit Daten
                    logger.debug("HID RX: OK response=0x%02X", data[5])
                    return DaliFrame(
                        is_response=True,
                        response_data=data[5]
                    )

                if status == HassebStatus.NO_ANSWER:
                    # Befehl gesendet, keine Antwort
                    logger.debug("HID RX: NO_ANSWER")
                    return DaliFrame(is_response=False)

                if status == HassebStatus.INVALID_ANSWER:
                    logger.warning("HID RX: INVALID_ANSWER")
                    return None

                if status == HassebStatus.ANSWER_TOO_EARLY:
                    logger.warning("HID RX: ANSWER_TOO_EARLY")
                    return None

        logger.warning("HID RX: Timeout")
        return DaliFrame(is_response=False) if not expect_reply else None

    def read_firmware(self) -> str:
        """Lese die Firmware-Version."""
        if not self._device:
            return 'unknown'

        seqnum = self._next_seqnum()
        data = struct.pack(
            'BBBBBBBBBB',
            HASSEB_PACKET_HEADER, HASSEB_READ_FIRMWARE_VERSION,
            seqnum, 0, 0, 0, 0, 0, 0, 0
        )

        try:
            self._device.write(data)
            for _ in range(100):
                response = self._device.read(10)
                if response and len(response) >= 5:
                    if response[1] == HASSEB_READ_FIRMWARE_VERSION:
                        return f"{response[3]}.{response[4]}"
                time.sleep(0.01)
        except Exception as e:
            logger.warning("Firmware-Version nicht lesbar: %s", e)

        return 'unknown'

    def enable_sniffing(self, callback=None):
        """Aktiviere den Sniffer-Modus."""
        self._sniffer_callback = callback
        self._sniffing = True
        self._send_config(0x01)
        logger.info("Hasseb Sniffer aktiviert")

    def disable_sniffing(self):
        """Deaktiviere den Sniffer-Modus."""
        self._sniffing = False
        self._sniffer_callback = None
        self._send_config(0x00)
        logger.info("Hasseb Sniffer deaktiviert")

    def sniff_frames(self, duration: float = 10.0) -> list:
        """Lausche auf dem Bus für die angegebene Dauer.

        Returns:
            Liste von (timestamp, byte_value, is_error) Tupeln.
            Jeweils 2 aufeinanderfolgende Bytes bilden ein DALI-Frame
            (Adressbyte + Datenbyte).
        """
        if not self._device:
            return []

        captured = []

        def on_sniffer_byte(byte_val, is_error):
            captured.append((time.time(), byte_val, is_error))

        self.enable_sniffing(callback=on_sniffer_byte)
        time.sleep(duration)
        self.disable_sniffing()

        # Rohe Bytes zu Frames zusammensetzen (je 2 Bytes = 1 Frame)
        frames = []
        i = 0
        while i + 1 < len(captured):
            ts = captured[i][0]
            addr = captured[i][1]
            cmd = captured[i + 1][1]
            is_error = captured[i][2] or captured[i + 1][2]
            frames.append({
                'ts': ts,
                'addr': addr,
                'cmd': cmd,
                'error': is_error
            })
            i += 2
        return frames

    def _send_config(self, value: int):
        """Sende Konfigurationsbefehl."""
        if not self._device:
            return
        seqnum = self._next_seqnum()
        data = struct.pack(
            'BBBBBBBBBB',
            HASSEB_PACKET_HEADER, HASSEB_CONFIGURE_DEVICE,
            seqnum, value, 0, 0, 0, 0, 0, 0
        )
        try:
            self._device.write(data)
        except Exception as e:
            logger.error("Config-Befehl fehlgeschlagen: %s", e)
