# =============================================================================
# DALI ServUI – DALI-Service-Layer
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Zentrale DALI-Kommunikationsschicht, orientiert am daliserver-Ansatz:
# - Queue-basiertes Command-Multiplexing
# - Austauschbare Treiber (Hasseb HID, MikroE GPIO, MikroE FTDI, Dryrun)
# - DT6 (LED Gear) und DT8 (Colour) Support
# - Timeout- und Error-Handling
# =============================================================================

import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional, Callable

from app.drivers.base import DaliDriver, DaliDriverConfig, DaliFrame
from app.drivers.registry import get_driver, list_drivers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fehlercodes (angelehnt an daliserver)
# ---------------------------------------------------------------------------
class DaliError(IntEnum):
    SUCCESS = 0           # Übertragung ok, keine Antwort
    RESPONSE = 1          # Übertragung ok, Antwort erhalten
    SEND_TIMEOUT = -1     # Timeout beim Senden
    RECEIVE_TIMEOUT = -2  # Timeout beim Empfangen
    SEND_ERROR = -3       # Fehler beim Senden
    RECEIVE_ERROR = -4    # Fehler beim Empfangen
    QUEUE_FULL = -5       # Befehlswarteschlange voll
    NO_DEVICE = -6        # Kein Gerät gefunden
    SYSTEM_ERROR = -7     # Allgemeiner Systemfehler


MAX_QUEUE_SIZE = 255
DEFAULT_COMMAND_TIMEOUT = 1.0
MAX_BUSLOG_SIZE = 500
MAX_SSE_LISTENERS = 50
MAX_JSON_BYTES = 5 * 1024 * 1024  # 5 MB Cap für persistente JSON-Dateien


# ---------------------------------------------------------------------------
# Datenstrukturen
# ---------------------------------------------------------------------------
@dataclass
class DaliTransaction:
    """Eine DALI-Transaktion in der Warteschlange."""
    address: int
    command: int
    expect_reply: bool = False
    send_twice: bool = False
    callback: Optional[Callable] = None
    timestamp: float = 0.0
    cancelled: bool = False

    def cancel(self):
        self.cancelled = True
        self.callback = None


@dataclass
class BusLogEntry:
    """Ein Eintrag im Bus-Protokoll."""
    timestamp: float
    direction: str           # 'TX' oder 'RX'
    address: int             # Adressbyte
    command: int             # Datenbyte
    response: int = -1       # Antwortbyte (-1 = keine)
    error: str = ''          # Fehlertext (leer = ok)
    expect_reply: bool = False
    send_twice: bool = False
    duration_ms: float = 0.0  # Dauer der Transaktion


@dataclass
class DaliResponse:
    """Antwort auf eine DALI-Transaktion."""
    error: DaliError
    response: int = 0
    address: int = 0
    command: int = 0


@dataclass
class DaliDevice:
    """Ein erkanntes DALI-Gerät auf dem Bus."""
    address: int
    device_type: int = 0
    groups: list = field(default_factory=list)
    level: int = 0
    min_level: int = 1
    max_level: int = 254
    status: int = 0
    present: bool = True
    # DT8 Colour-Daten
    colour_type: int = 0         # Colour Type Features (Bitmask)
    colour_temp_mirek: int = 0   # Aktuelle Farbtemperatur in Mirek (0 = nicht gesetzt)
    colour_temp_min: int = 153   # Min Tc Mirek (~6500K kalt)
    colour_temp_max: int = 370   # Max Tc Mirek (~2700K warm)
    rgb_r: int = 0               # Rot 0..254
    rgb_g: int = 0               # Gruen 0..254
    rgb_b: int = 0               # Blau 0..254
    supports_tc: bool = False    # Unterstützt Tunable White
    supports_rgb: bool = False   # Unterstützt RGBWAF


# ---------------------------------------------------------------------------
# Konfigurations-Persistierung
# ---------------------------------------------------------------------------
CONFIG_FILE = 'driver_config.json'
LABELS_FILE = 'labels.json'
DEVICES_FILE = 'devices.json'
DASHBOARDS_FILE = 'dashboards.json'


def _safe_json_load(path: str):
    """Lade JSON aus Pfad mit Größen-Cap (MAX_JSON_BYTES).
    Gibt None zurück wenn Datei nicht existiert, zu groß ist oder
    nicht parsbar."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size > MAX_JSON_BYTES:
        logger.warning(
            "JSON-Datei zu gross (%d Bytes > %d), wird ignoriert: %s",
            size, MAX_JSON_BYTES, path)
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("JSON-Datei nicht lesbar (%s): %s", exc, path)
        return None


# Typisierte Whitelist für load_driver_config – Werte mit falschem Typ werden
# verworfen, damit ein manipuliertes JSON keine unerwarteten Zustände erzeugt.
_DRIVER_CONFIG_FIELDS = {
    'driver_id': str,
    'hasseb_vendor': int,
    'hasseb_product': int,
    'gpio_tx_pin': int,
    'gpio_rx_pin': int,
    'gpio_tx_inverted': bool,
    'gpio_chip': str,
    'ftdi_url': str,
    'ftdi_tx_pin': int,
    'ftdi_rx_pin': int,
    'ftdi_tx_inverted': bool,
    'ftdi_rx_inverted': bool,
    'feature_dt6': bool,
    'feature_dt8_tc': bool,
    'feature_dt8_rgb': bool,
}


def load_driver_config(data_dir: str) -> DaliDriverConfig:
    """Lade die Treiber-Konfiguration aus der JSON-Datei (typsicher)."""
    config = DaliDriverConfig()
    path = os.path.join(data_dir, CONFIG_FILE)

    data = _safe_json_load(path)
    if not isinstance(data, dict):
        return config

    for key, expected_type in _DRIVER_CONFIG_FIELDS.items():
        if key not in data:
            continue
        value = data[key]
        # Bool darf nicht aus int kommen (in Python ist bool subclass von int)
        if expected_type is bool and not isinstance(value, bool):
            continue
        if expected_type is int and isinstance(value, bool):
            continue
        if not isinstance(value, expected_type):
            continue
        setattr(config, key, value)

    logger.info("Treiber-Konfiguration geladen: %s", config.driver_id)
    return config


def save_driver_config(data_dir: str, config: DaliDriverConfig):
    """Speichere die Treiber-Konfiguration als JSON."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, CONFIG_FILE)

    data = {
        'driver_id': config.driver_id,
        'hasseb_vendor': config.hasseb_vendor,
        'hasseb_product': config.hasseb_product,
        'gpio_tx_pin': config.gpio_tx_pin,
        'gpio_rx_pin': config.gpio_rx_pin,
        'gpio_tx_inverted': config.gpio_tx_inverted,
        'gpio_chip': config.gpio_chip,
        'ftdi_url': config.ftdi_url,
        'ftdi_tx_pin': config.ftdi_tx_pin,
        'ftdi_rx_pin': config.ftdi_rx_pin,
        'ftdi_tx_inverted': config.ftdi_tx_inverted,
        'ftdi_rx_inverted': config.ftdi_rx_inverted,
        'feature_dt6': config.feature_dt6,
        'feature_dt8_tc': config.feature_dt8_tc,
        'feature_dt8_rgb': config.feature_dt8_rgb,
    }

    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Treiber-Konfiguration gespeichert: %s", config.driver_id)
    except Exception as e:
        logger.error("Konfig konnte nicht gespeichert werden: %s", e)


# ---------------------------------------------------------------------------
# Label-Persistierung (Geräte- und Gruppennamen)
# ---------------------------------------------------------------------------
def load_labels(data_dir: str) -> dict:
    """Lade Labels aus JSON. Format: {"devices": {"0": "Name"}, "groups": {"0": "Name"}}"""
    path = os.path.join(data_dir, LABELS_FILE)
    default = {'devices': {}, 'groups': {}}
    data = _safe_json_load(path)
    if isinstance(data, dict):
        return {
            'devices': data.get('devices', {}) if isinstance(data.get('devices'), dict) else {},
            'groups': data.get('groups', {}) if isinstance(data.get('groups'), dict) else {}
        }
    return default


def save_labels(data_dir: str, labels: dict):
    """Speichere Labels als JSON."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, LABELS_FILE)
    try:
        with open(path, 'w') as f:
            json.dump(labels, f, indent=2, ensure_ascii=False)
        logger.info("Labels gespeichert")
    except Exception as e:
        logger.error("Labels konnten nicht gespeichert werden: %s", e)


# ---------------------------------------------------------------------------
# Geräte-Persistierung (Scan-Ergebnisse)
# ---------------------------------------------------------------------------
def load_devices(data_dir: str) -> dict:
    """Lade gespeicherte Geräte aus JSON."""
    path = os.path.join(data_dir, DEVICES_FILE)
    data = _safe_json_load(path)
    if not isinstance(data, dict):
        return {}
    devices = {}
    try:
        for addr_str, dev_data in data.items():
            try:
                addr = int(addr_str)
            except (TypeError, ValueError):
                continue
            if not isinstance(dev_data, dict):
                continue
            device = DaliDevice(address=addr)
            for key, value in dev_data.items():
                if hasattr(device, key):
                    setattr(device, key, value)
            devices[addr] = device
    except Exception as e:
        logger.warning("Gerätedaten nicht lesbar: %s", e)
        return {}
    logger.info("Gerätedaten geladen: %d Geräte", len(devices))
    return devices


def save_devices(data_dir: str, devices: dict):
    """Speichere Geräte als JSON."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, DEVICES_FILE)
    data = {}
    for addr, dev in devices.items():
        data[str(addr)] = {
            'address': dev.address,
            'device_type': dev.device_type,
            'groups': dev.groups,
            'level': dev.level,
            'min_level': dev.min_level,
            'max_level': dev.max_level,
            'status': dev.status,
            'present': dev.present,
            'colour_type': dev.colour_type,
            'colour_temp_mirek': dev.colour_temp_mirek,
            'colour_temp_min': dev.colour_temp_min,
            'colour_temp_max': dev.colour_temp_max,
            'supports_tc': dev.supports_tc,
            'supports_rgb': dev.supports_rgb,
        }
    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("Gerätedaten gespeichert: %d Geräte", len(data))
    except Exception as e:
        logger.error("Gerätedaten konnten nicht gespeichert werden: %s", e)


# ---------------------------------------------------------------------------
# Dashboard-Persistierung
# ---------------------------------------------------------------------------
DEFAULT_DASHBOARDS = {
    'dashboards': {
        'default': {
            'name': 'Übersicht',
            'order': 0,
            'show_status_cards': True,
            'show_broadcast': True,
            'items': [{'type': 'all_devices'}]
        }
    },
    'active': 'default'
}


def load_dashboards(data_dir: str) -> dict:
    """Lade Dashboard-Konfigurationen aus JSON."""
    path = os.path.join(data_dir, DASHBOARDS_FILE)
    data = _safe_json_load(path)
    if (isinstance(data, dict)
            and isinstance(data.get('dashboards'), dict)
            and 'default' in data['dashboards']):
        return data
    return json.loads(json.dumps(DEFAULT_DASHBOARDS))


def save_dashboards(data_dir: str, dashboards: dict):
    """Speichere Dashboard-Konfigurationen als JSON."""
    os.makedirs(data_dir, exist_ok=True)
    path = os.path.join(data_dir, DASHBOARDS_FILE)
    try:
        with open(path, 'w') as f:
            json.dump(dashboards, f, indent=2, ensure_ascii=False)
        logger.info("Dashboard-Konfiguration gespeichert")
    except Exception as e:
        logger.error("Dashboard-Konfiguration konnte nicht gespeichert werden: %s", e)


# ---------------------------------------------------------------------------
# DALI-Frame-Beschreibung (für Bus-Log)
# ---------------------------------------------------------------------------
def _describe_dali_frame(address: int, command: int) -> str:
    """Liefert eine lesbare Beschreibung eines DALI Forward Frames."""
    # Spezial-Adressen (Broadcast, Config-Befehle)
    if address == 0xFF:
        return f'Broadcast DAPC {command}'
    if address == 0xFE:
        return f'Broadcast Off' if command == 0 else f'Broadcast Cmd {command}'
    if address == 0xA3:
        return f'DTR0 = {command} (0x{command:02X})'
    if address == 0xC3:
        return f'DTR1 = {command} (0x{command:02X})'
    if address == 0xC5:
        return f'DTR2 = {command} (0x{command:02X})'
    if address == 0xC1:
        return f'EnableDeviceType({command})'
    if address == 0xA5:
        return 'Initialise'
    if address == 0xA7:
        return 'Randomise'
    if address == 0xA9:
        return 'Compare'
    if address == 0xB1:
        return f'SearchAddrH = {command}'
    if address == 0xB3:
        return f'SearchAddrM = {command}'
    if address == 0xB5:
        return f'SearchAddrL = {command}'
    if address == 0xB7:
        return f'ProgramShortAddr = {command >> 1}'
    if address == 0xAB:
        return 'Withdraw'
    if address == 0xB9:
        return f'VerifyShortAddr = {command >> 1}'

    # Geräte-Adresse (Bit 0 unterscheidet DAPC vs. Befehl)
    if (address & 0x01) == 0:
        # DAPC – Direct Arc Power Control
        short_addr = (address >> 1) & 0x3F
        return f'Addr {short_addr} DAPC {command}'

    # Befehl an Einzeladresse
    short_addr = (address >> 1) & 0x3F
    cmd_names = {
        0x00: 'Off', 0x01: 'Up', 0x02: 'Down',
        0x03: 'StepUp', 0x04: 'StepDown',
        0x05: 'RecallMaxLevel', 0x06: 'RecallMinLevel',
        0x07: 'StepDown+Off', 0x08: 'On+StepUp',
        0x20: 'Reset', 0x2A: 'StoreDTRAsPowerOnLevel',
        0x90: 'QueryStatus', 0x93: 'QueryDeviceType',
        0xA0: 'QueryActualLevel', 0xA1: 'QueryMaxLevel',
        0xA2: 'QueryMinLevel', 0xC0: 'QueryGroupsL',
        0xC1: 'QueryGroupsH',
        0xE2: 'DT8:Activate', 0xE7: 'DT8:SetTempColourTc',
        0xEB: 'DT8:SetTempRGBDimlevel', 0xF9: 'DT8:QueryColourTypeFeatures',
        0xFA: 'DT8:QueryColourValue',
        0xF1: 'DT6:QueryFeatures', 0xF4: 'DT6:QueryOperatingMode',
        0xF5: 'DT6:QueryPossibleOperatingModes',
    }
    name = cmd_names.get(command, f'Cmd 0x{command:02X}')
    return f'Addr {short_addr} {name}'


# ---------------------------------------------------------------------------
# DALI-Service – Hauptklasse
# ---------------------------------------------------------------------------
class DaliService:
    """Zentraler DALI-Kommunikationsservice mit austauschbarem Treiber.

    Architektur nach daliserver-Vorbild:
    - Befehle werden in eine Queue eingereiht
    - Ein Worker-Thread arbeitet die Queue sequentiell ab
    - Der aktive Treiber kann zur Laufzeit gewechselt werden (über WebUI)
    """

    def __init__(self, data_dir: str = ''):
        self._data_dir = data_dir
        self._driver: Optional[DaliDriver] = None
        self._driver_config = DaliDriverConfig()
        self._queue = deque()
        self._queue_lock = threading.Lock()
        self._running = False
        self._worker_thread = None
        self._devices = {}
        self._devices_lock = threading.Lock()
        self._broadcast_listeners = []
        self._broadcast_lock = threading.Lock()
        self._buslog = deque(maxlen=MAX_BUSLOG_SIZE)
        self._buslog_lock = threading.Lock()
        self._buslog_enabled = True
        self._event_listeners = []
        self._event_lock = threading.Lock()
        self._labels = {'devices': {}, 'groups': {}}
        if data_dir:
            self._labels = load_labels(data_dir)
            self._devices = load_devices(data_dir)

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------
    def start(self, driver_id: str = '', config: Optional[DaliDriverConfig] = None) -> DaliError:
        """Starte den Service mit dem angegebenen Treiber.

        Args:
            driver_id: Treiber-ID (leer = aus Config laden)
            config: Treiber-Konfiguration (None = aus Config laden)

        Returns:
            DaliError.SUCCESS bei Erfolg
        """
        if self._running:
            logger.warning("Service läuft bereits")
            return DaliError.SUCCESS

        # Konfiguration laden
        if config:
            self._driver_config = config
        elif self._data_dir:
            self._driver_config = load_driver_config(self._data_dir)

        if driver_id:
            self._driver_config.driver_id = driver_id

        # Treiber erstellen und öffnen
        self._driver = get_driver(
            self._driver_config.driver_id, self._driver_config
        )
        if not self._driver:
            logger.error("Treiber '%s' nicht verfügbar",
                         self._driver_config.driver_id)
            # Fallback auf Dryrun
            self._driver_config.driver_id = 'dryrun'
            self._driver = get_driver('dryrun', self._driver_config)

        if not self._driver.open():
            logger.error("Treiber konnte nicht geöffnet werden")
            return DaliError.NO_DEVICE

        # Worker-Thread starten
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            name="dali-worker",
            daemon=True
        )
        self._worker_thread.start()

        logger.info("DALI-Service gestartet (Treiber: %s)",
                     self._driver_config.driver_id)

        # Aktuelle Level vom Bus abfragen (im Hintergrund)
        if self._devices:
            threading.Thread(
                target=self._refresh_device_levels,
                name="level-refresh",
                daemon=True
            ).start()

        return DaliError.SUCCESS

    def stop(self):
        """Stoppe den Service."""
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=3.0)
            self._worker_thread = None
        if self._driver:
            self._driver.close()
            self._driver = None
        logger.info("DALI-Service gestoppt")

    def switch_driver(self, driver_id: str,
                      config: Optional[DaliDriverConfig] = None) -> DaliError:
        """Wechsle den Treiber zur Laufzeit (aus WebUI).

        Stoppt den aktuellen Treiber, startet den neuen.

        Args:
            driver_id: Neue Treiber-ID
            config: Neue Konfiguration (None = bestehende nutzen)

        Returns:
            DaliError.SUCCESS bei Erfolg
        """
        logger.info("Wechsle Treiber zu '%s'...", driver_id)
        was_running = self._running
        self.stop()

        if config:
            self._driver_config = config
        self._driver_config.driver_id = driver_id

        # Konfiguration persistieren
        if self._data_dir:
            save_driver_config(self._data_dir, self._driver_config)

        if was_running:
            return self.start(driver_id=driver_id, config=self._driver_config)
        return DaliError.SUCCESS

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_connected(self) -> bool:
        return self._driver is not None and self._driver.is_open

    @property
    def firmware_version(self) -> str:
        return self._driver.firmware_version if self._driver else 'unknown'

    @property
    def active_driver_id(self) -> str:
        return self._driver_config.driver_id

    @property
    def driver_config(self) -> DaliDriverConfig:
        return self._driver_config

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    # -------------------------------------------------------------------
    # Befehl einreihen
    # -------------------------------------------------------------------
    def send_command(self, address: int, command: int,
                     expect_reply: bool = False, send_twice: bool = False,
                     callback: Optional[Callable] = None) -> DaliError:
        """Reihe einen DALI-Befehl in die Warteschlange ein."""
        with self._queue_lock:
            if len(self._queue) >= MAX_QUEUE_SIZE:
                if callback:
                    callback(DaliResponse(error=DaliError.QUEUE_FULL))
                return DaliError.QUEUE_FULL

            self._queue.append(DaliTransaction(
                address=address, command=command,
                expect_reply=expect_reply, send_twice=send_twice,
                callback=callback, timestamp=time.time()
            ))
        return DaliError.SUCCESS

    def send_command_sync(self, address: int, command: int,
                          expect_reply: bool = False,
                          send_twice: bool = False,
                          timeout: float = DEFAULT_COMMAND_TIMEOUT) -> DaliResponse:
        """Sende einen DALI-Befehl synchron."""
        result_event = threading.Event()
        result_holder = [None]

        def on_response(response):
            result_holder[0] = response
            result_event.set()

        error = self.send_command(
            address=address, command=command,
            expect_reply=expect_reply, send_twice=send_twice,
            callback=on_response
        )
        if error != DaliError.SUCCESS:
            return DaliResponse(error=error)

        if result_event.wait(timeout=timeout):
            return result_holder[0]
        return DaliResponse(error=DaliError.RECEIVE_TIMEOUT)

    # -------------------------------------------------------------------
    # SSE-Event-System (für Echtzeit-Updates an Clients)
    # -------------------------------------------------------------------
    def subscribe_events(self) -> 'queue.Queue':
        """Neuen SSE-Client registrieren. Gibt eine Queue zurück.
        Wirft RuntimeError, wenn die maximale Anzahl gleichzeitiger
        SSE-Clients (MAX_SSE_LISTENERS) bereits erreicht ist."""
        import queue
        with self._event_lock:
            if len(self._event_listeners) >= MAX_SSE_LISTENERS:
                raise RuntimeError(
                    f"Maximale SSE-Clients erreicht ({MAX_SSE_LISTENERS})")
            q = queue.Queue(maxsize=50)
            self._event_listeners.append(q)
        return q

    def unsubscribe_events(self, q):
        """SSE-Client abmelden."""
        with self._event_lock:
            try:
                self._event_listeners.remove(q)
            except ValueError:
                pass

    def _emit_event(self, event_type: str, data: dict):
        """Event an alle registrierten SSE-Clients senden."""
        with self._event_lock:
            dead = []
            for q in self._event_listeners:
                try:
                    q.put_nowait({'event': event_type, **data})
                except Exception:
                    dead.append(q)
            for q in dead:
                self._event_listeners.remove(q)

    # -------------------------------------------------------------------
    # Broadcast-Listener
    # -------------------------------------------------------------------
    def add_broadcast_listener(self, listener: Callable):
        with self._broadcast_lock:
            self._broadcast_listeners.append(listener)

    def remove_broadcast_listener(self, listener: Callable):
        with self._broadcast_lock:
            try:
                self._broadcast_listeners.remove(listener)
            except ValueError:
                pass

    # -------------------------------------------------------------------
    # Worker-Thread
    # -------------------------------------------------------------------
    def _worker_loop(self):
        """Hauptschleife: Queue sequentiell abarbeiten."""
        while self._running:
            transaction = None
            with self._queue_lock:
                if self._queue:
                    transaction = self._queue.popleft()

            if transaction and not transaction.cancelled:
                self._process_transaction(transaction)
            else:
                time.sleep(0.01)

    def _process_transaction(self, transaction: DaliTransaction):
        """Verarbeite eine Transaktion über den aktiven Treiber."""
        if not self._driver or not self._driver.is_open:
            self._log_bus_entry(transaction, None, DaliError.NO_DEVICE, 0.0)
            self._deliver(transaction, DaliResponse(error=DaliError.NO_DEVICE))
            return

        t_start = time.perf_counter()
        frame = self._driver.send_frame(
            address=transaction.address,
            command=transaction.command,
            expect_reply=transaction.expect_reply,
            send_twice=transaction.send_twice
        )
        duration_ms = (time.perf_counter() - t_start) * 1000

        if frame is None:
            self._log_bus_entry(transaction, None, DaliError.SEND_ERROR, duration_ms)
            self._deliver(transaction, DaliResponse(error=DaliError.SEND_ERROR))
        elif frame.is_response:
            self._log_bus_entry(
                transaction, frame.response_data, DaliError.RESPONSE, duration_ms
            )
            self._deliver(transaction, DaliResponse(
                error=DaliError.RESPONSE,
                response=frame.response_data
            ))
        else:
            self._log_bus_entry(transaction, None, DaliError.SUCCESS, duration_ms)
            self._deliver(transaction, DaliResponse(error=DaliError.SUCCESS))

    def _deliver(self, transaction: DaliTransaction, response: DaliResponse):
        """Liefere die Antwort an den Callback."""
        if transaction.cancelled or not transaction.callback:
            return
        try:
            transaction.callback(response)
        except Exception as e:
            logger.error("Callback-Fehler: %s", e)

    # -------------------------------------------------------------------
    # Bus-Protokoll (Ringbuffer)
    # -------------------------------------------------------------------
    def _log_bus_entry(self, transaction: DaliTransaction,
                       response_data, error: DaliError, duration_ms: float):
        """Füge einen Eintrag zum Bus-Protokoll hinzu."""
        if not self._buslog_enabled:
            return
        entry = BusLogEntry(
            timestamp=time.time(),
            direction='TX',
            address=transaction.address,
            command=transaction.command,
            response=response_data if response_data is not None else -1,
            error=error.name if error < 0 else '',
            expect_reply=transaction.expect_reply,
            send_twice=transaction.send_twice,
            duration_ms=round(duration_ms, 2)
        )
        with self._buslog_lock:
            self._buslog.append(entry)

    def get_buslog(self, limit: int = 100, since: float = 0.0) -> list:
        """Hole die letzten Bus-Log-Einträge.

        Args:
            limit: Maximale Anzahl Einträge
            since: Nur Einträge nach diesem Timestamp (für Polling)

        Returns:
            Liste von BusLogEntry als Dicts
        """
        with self._buslog_lock:
            entries = list(self._buslog)
        if since > 0:
            entries = [e for e in entries if e.timestamp > since]
        entries = entries[-limit:]
        return [
            {
                'ts': e.timestamp,
                'dir': e.direction,
                'addr': e.address,
                'addr_hex': f'0x{e.address:02X}',
                'cmd': e.command,
                'cmd_hex': f'0x{e.command:02X}',
                'resp': e.response,
                'resp_hex': f'0x{e.response:02X}' if e.response >= 0 else '–',
                'error': e.error,
                'expect_reply': e.expect_reply,
                'twice': e.send_twice,
                'ms': e.duration_ms,
                'desc': _describe_dali_frame(e.address, e.command)
            }
            for e in entries
        ]

    def clear_buslog(self):
        """Bus-Protokoll löschen."""
        with self._buslog_lock:
            self._buslog.clear()

    @property
    def buslog_enabled(self) -> bool:
        return self._buslog_enabled

    @buslog_enabled.setter
    def buslog_enabled(self, value: bool):
        self._buslog_enabled = value

    # -------------------------------------------------------------------
    # High-Level DALI-Befehle
    # -------------------------------------------------------------------
    def _update_device_level(self, address: int, level: int):
        """Geräte-Level im Speicher aktualisieren."""
        with self._devices_lock:
            if address == 255:
                # Broadcast: alle Geräte aktualisieren
                for dev in self._devices.values():
                    dev.level = level
            elif address in self._devices:
                self._devices[address].level = level
        self._persist_devices()

    def _update_group_level(self, group: int, level: int):
        """Level aller Geräte einer Gruppe im Speicher aktualisieren."""
        with self._devices_lock:
            for dev in self._devices.values():
                if group in dev.groups:
                    dev.level = level
        self._persist_devices()

    def set_level(self, address: int, level: int) -> DaliResponse:
        """DAPC – Direct Arc Power Control (Helligkeit setzen)."""
        if address == 255:
            addr_byte = 0xFE  # Broadcast DAPC
        else:
            addr_byte = (address & 0x3F) << 1
        resp = self.send_command_sync(
            address=addr_byte, command=level & 0xFF
        )
        self._update_device_level(address, level)
        self._emit_event('level', {
            'address': address, 'level': level
        })
        return resp

    def turn_on(self, address: int) -> DaliResponse:
        """Gerät einschalten (Recall Max Level)."""
        if address == 255:
            addr_byte = 0xFF
        else:
            addr_byte = ((address & 0x3F) << 1) | 0x01
        resp = self.send_command_sync(address=addr_byte, command=0x05)
        self._update_device_level(address, 254)
        self._emit_event('on', {'address': address})
        return resp

    def turn_off(self, address: int) -> DaliResponse:
        """Gerät ausschalten."""
        if address == 255:
            addr_byte = 0xFF
        else:
            addr_byte = ((address & 0x3F) << 1) | 0x01
        resp = self.send_command_sync(address=addr_byte, command=0x00)
        self._update_device_level(address, 0)
        self._emit_event('off', {'address': address})
        return resp

    def query_status(self, address: int) -> DaliResponse:
        addr_byte = ((address & 0x3F) << 1) | 0x01
        return self.send_command_sync(
            address=addr_byte, command=0x90, expect_reply=True
        )

    def query_actual_level(self, address: int) -> DaliResponse:
        addr_byte = ((address & 0x3F) << 1) | 0x01
        return self.send_command_sync(
            address=addr_byte, command=0xA0, expect_reply=True
        )

    def query_device_present(self, address: int) -> bool:
        """QueryControlGearPresent mit Retry bei Fehler."""
        addr_byte = ((address & 0x3F) << 1) | 0x01
        for attempt in range(2):
            resp = self.send_command_sync(
                address=addr_byte, command=0x91, expect_reply=True
            )
            if resp.error == DaliError.RESPONSE:
                return True
            if resp.error >= 0:  # SUCCESS oder RESPONSE = kein Fehler
                return False
            # SEND_ERROR oder anderer Fehler: kurz warten und retry
            if attempt == 0:
                time.sleep(0.1)
                logger.debug("Retry query_device_present addr=%d", address)
        return False

    def query_device_type(self, address: int) -> DaliResponse:
        addr_byte = ((address & 0x3F) << 1) | 0x01
        return self.send_command_sync(
            address=addr_byte, command=0x99, expect_reply=True
        )

    def query_groups(self, address: int) -> list:
        addr_byte = ((address & 0x3F) << 1) | 0x01
        r1 = self.send_command_sync(
            address=addr_byte, command=0xC0, expect_reply=True
        )
        r2 = self.send_command_sync(
            address=addr_byte, command=0xC1, expect_reply=True
        )
        groups = []
        if r1.error == DaliError.RESPONSE:
            for bit in range(8):
                if r1.response & (1 << bit):
                    groups.append(bit)
        if r2.error == DaliError.RESPONSE:
            for bit in range(8):
                if r2.response & (1 << bit):
                    groups.append(8 + bit)
        return groups

    def _refresh_device_levels(self):
        """Aktuelle Level aller bekannten Geräte vom Bus abfragen."""
        logger.info("Level-Refresh: Frage aktuelle Level vom Bus ab...")
        updated = 0
        with self._devices_lock:
            addresses = list(self._devices.keys())

        for addr in addresses:
            if not self._running:
                break
            resp = self.query_actual_level(addr)
            if resp.error == DaliError.RESPONSE:
                with self._devices_lock:
                    if addr in self._devices:
                        self._devices[addr].level = resp.response
                        updated += 1

        self._persist_devices()
        logger.info("Level-Refresh: %d Geräte aktualisiert", updated)

    # -------------------------------------------------------------------
    # Gruppen-Steuerung
    # -------------------------------------------------------------------
    def group_on(self, group: int) -> DaliResponse:
        addr_byte = 0x80 | ((group & 0x0F) << 1) | 0x01
        resp = self.send_command_sync(address=addr_byte, command=0x05)
        self._update_group_level(group, 254)
        self._emit_event('group_on', {'group': group})
        return resp

    def group_off(self, group: int) -> DaliResponse:
        addr_byte = 0x80 | ((group & 0x0F) << 1) | 0x01
        resp = self.send_command_sync(address=addr_byte, command=0x00)
        self._update_group_level(group, 0)
        self._emit_event('group_off', {'group': group})
        return resp

    def group_level(self, group: int, level: int) -> DaliResponse:
        addr_byte = 0x80 | ((group & 0x0F) << 1)
        resp = self.send_command_sync(
            address=addr_byte, command=level & 0xFF
        )
        self._update_group_level(group, level)
        self._emit_event('group_level', {'group': group, 'level': level})
        return resp

    # -------------------------------------------------------------------
    # Gruppen-Zuweisung (DALI-Befehle)
    # -------------------------------------------------------------------
    def add_to_group(self, address: int, group: int) -> DaliResponse:
        """Füge ein Gerät einer Gruppe hinzu (DALI AddToGroup 0x60-0x6F)."""
        if group < 0 or group > 15:
            return DaliResponse(error=DaliError.SYSTEM_ERROR)
        addr_byte = ((address & 0x3F) << 1) | 0x01
        resp = self.send_command_sync(
            address=addr_byte, command=0x60 + group, send_twice=True
        )
        # Lokale Device-Daten aktualisieren
        with self._devices_lock:
            if address in self._devices:
                if group not in self._devices[address].groups:
                    self._devices[address].groups.append(group)
                    self._devices[address].groups.sort()
        self._persist_devices()
        logger.info("Gerät %d zu Gruppe %d hinzugefügt", address, group)
        return resp

    def remove_from_group(self, address: int, group: int) -> DaliResponse:
        """Entferne ein Gerät aus einer Gruppe (DALI RemoveFromGroup 0x70-0x7F)."""
        if group < 0 or group > 15:
            return DaliResponse(error=DaliError.SYSTEM_ERROR)
        addr_byte = ((address & 0x3F) << 1) | 0x01
        resp = self.send_command_sync(
            address=addr_byte, command=0x70 + group, send_twice=True
        )
        with self._devices_lock:
            if address in self._devices:
                if group in self._devices[address].groups:
                    self._devices[address].groups.remove(group)
        self._persist_devices()
        logger.info("Gerät %d aus Gruppe %d entfernt", address, group)
        return resp

    # -------------------------------------------------------------------
    # Labels (Geräte- und Gruppennamen)
    # -------------------------------------------------------------------
    def get_labels(self) -> dict:
        return dict(self._labels)

    def set_device_label(self, address: int, name: str):
        self._labels['devices'][str(address)] = name
        if self._data_dir:
            save_labels(self._data_dir, self._labels)

    def set_group_label(self, group: int, name: str):
        self._labels['groups'][str(group)] = name
        if self._data_dir:
            save_labels(self._data_dir, self._labels)

    def get_device_label(self, address: int) -> str:
        return self._labels['devices'].get(str(address), '')

    def get_group_label(self, group: int) -> str:
        return self._labels['groups'].get(str(group), '')

    def _persist_devices(self):
        """Gerätedaten in JSON speichern."""
        if self._data_dir:
            with self._devices_lock:
                save_devices(self._data_dir, self._devices)

    def get_devices(self) -> dict:
        with self._devices_lock:
            return dict(self._devices)

    # -------------------------------------------------------------------
    # Commissioning
    # -------------------------------------------------------------------
    def reset_addresses(self):
        """Alle Kurzadressen auf dem Bus löschen.

        Setzt DTR0=0xFF (=keine Adresse) und sendet Broadcast
        'Store DTR as Short Address'. Danach hat kein Gerät
        mehr eine Kurzadresse – Commissioning nötig.
        """
        logger.info("Lösche alle Kurzadressen auf dem Bus...")

        # DTR0 = 0xFF (MASK = keine Adresse)
        self.send_command_sync(address=0xA3, command=0xFF)
        time.sleep(0.05)

        # Initialise all (nötig damit Store-Befehl akzeptiert wird)
        self.send_command_sync(address=0xA5, command=0xFF, send_twice=True)
        time.sleep(0.1)

        # DTR0 nochmal setzen (Initialise könnte DTR überschrieben haben)
        self.send_command_sync(address=0xA3, command=0xFF)
        time.sleep(0.05)

        # Broadcast: Store DTR as Short Address (0x80, 2× senden)
        # Adressbyte 0xFF = Broadcast + Command-Modus
        self.send_command_sync(address=0xFF, command=0x80, send_twice=True)
        time.sleep(0.1)

        # Terminate
        self.send_command_sync(address=0xA1, command=0x00, send_twice=True)
        time.sleep(0.05)

        # Lokale Gerätedaten löschen
        with self._devices_lock:
            self._devices = {}
        self._persist_devices()
        logger.info("Alle Kurzadressen gelöscht")

    def reset_bus_factory(self):
        """Vollständiger DALI Factory Reset (Broadcast).

        Setzt alle Geräte auf Werkseinstellungen zurück:
        Kurzadressen, Gruppen, Szenen, Min/Max-Level – alles weg.
        """
        logger.info("Factory Reset auf dem gesamten Bus...")

        # Broadcast RESET (Befehl 0x20, 2× senden)
        # Adressbyte 0xFF = Broadcast Command
        self.send_command_sync(address=0xFF, command=0x20, send_twice=True)
        time.sleep(0.5)

        # Lokale Gerätedaten löschen
        with self._devices_lock:
            self._devices = {}
        self._persist_devices()
        logger.info("Factory Reset abgeschlossen")

    def initialize_bus(self, broadcast: bool = True) -> list:
        """Commissioning via python-dali (zuverlässiger als eigene Impl.).

        Nutzt python-dali's Hasseb-Treiber und Commissioning-Sequenz,
        da diese nachweislich stabil mit dem Hasseb USB funktioniert.
        Unsere eigene Implementierung crasht den Hasseb bei Compare.

        Für andere Treiber (FTDI, GPIO) wird die eigene Implementierung
        als Fallback genutzt.
        """
        # Bei Hasseb: python-dali nutzen (bewährt und stabil)
        if self._driver_config.driver_id == 'hasseb':
            return self._commission_via_python_dali(broadcast)
        # Andere Treiber: eigene Implementierung
        return self._commission_native(broadcast)

    def _commission_via_python_dali(self, broadcast: bool) -> list:
        """Commissioning über python-dali Subprocess.

        Nutzt python-dali v0.11 API: SyncHassebDALIUSBDriver.run_sequence()
        mit Commissioning()-Generator. Nachweislich stabil mit 20+ EVGs.

        Stoppt den eigenen Hasseb-Treiber, lässt python-dali das
        Commissioning durchführen, und startet den Treiber danach neu.
        """
        logger.info("Commissioning via python-dali (broadcast=%s)...", broadcast)

        # Eigenen Treiber schliessen (python-dali braucht exklusiven Zugriff)
        if self._driver:
            self._driver.close()
            logger.info("Hasseb-Treiber geschlossen für python-dali")

        try:
            script = (
                "from dali.driver.hasseb import SyncHassebDALIUSBDriver as Drv\n"
                "from dali.gear.general import Reset, QueryControlGearPresent\n"
                "from dali.address import Broadcast, Short\n"
                "from dali.sequences import Commissioning\n"
                "import time\n"
                "\n"
                "drv = Drv()\n"
                "\n"
                "# Factory Reset (2x senden, Config-Befehl)\n"
                "drv.send(Reset(Broadcast()))\n"
                "time.sleep(0.1)\n"
                "drv.send(Reset(Broadcast()))\n"
                "time.sleep(3.0)\n"
                "\n"
                "# Commissioning via run_sequence\n"
                "def on_progress(p):\n"
                "    print(f'PROGRESS:{p}')\n"
                "\n"
                "drv.run_sequence(Commissioning(), progress_cb=on_progress)\n"
                "\n"
                "# Adress-Check: Welche Adressen antworten?\n"
                "found = 0\n"
                "for addr in range(64):\n"
                "    resp = drv.send(QueryControlGearPresent(Short(addr)))\n"
                "    if resp and resp.raw_value is not None:\n"
                "        print(f'SA={addr}')\n"
                "        found += 1\n"
                "\n"
                "print(f'TOTAL={found}')\n"
                "try: drv.close()\n"
                "except: pass\n"
            )

            result = subprocess.run(
                [sys.executable, '-c', script],
                capture_output=True, text=True, timeout=300
            )

            assigned = []
            for line in result.stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith('SA='):
                    try:
                        sa = int(line.split('SA=')[1].split()[0])
                        assigned.append(DaliDevice(address=sa))
                        logger.info("python-dali: %s", line)
                    except (ValueError, IndexError):
                        pass
                elif line.startswith('TOTAL='):
                    logger.info("python-dali: %s", line)

            if result.returncode != 0 and result.stderr:
                logger.warning("python-dali stderr: %s",
                               result.stderr[:500])

            logger.info("Commissioning via python-dali: %d Geräte",
                        len(assigned))
            return assigned

        except FileNotFoundError:
            logger.error("python-dali nicht installiert")
            return []
        except subprocess.TimeoutExpired:
            logger.error("Commissioning Timeout (5 Min)")
            return []
        except Exception as e:
            logger.error("Commissioning Fehler: %s", e)
            return []
        finally:
            # Eigenen Treiber wieder öffnen
            time.sleep(1.0)
            if self._driver:
                if self._driver.open():
                    logger.info("Hasseb-Treiber nach Commissioning neu geöffnet")
                else:
                    logger.error("Hasseb-Treiber konnte nicht neu geöffnet werden")

    def _commission_native(self, broadcast: bool) -> list:
        """Eigenes Commissioning (für FTDI/GPIO-Treiber)."""
        logger.info("Starte natives Commissioning (broadcast=%s)...", broadcast)

        self.send_command_sync(address=0xA1, command=0x00, send_twice=True)
        time.sleep(0.05)

        init_cmd = 0xFF if broadcast else 0x00
        self.send_command_sync(address=0xA5, command=init_cmd, send_twice=True)
        time.sleep(0.1)

        self.send_command_sync(address=0xA7, command=0x00, send_twice=True)
        time.sleep(0.5)

        assigned = []
        next_address = 0

        for _ in range(64):
            if not self._running:
                break
            found = self._find_next_device()
            if found is None:
                break

            short_addr = next_address
            self.send_command_sync(
                address=0xB7,
                command=(short_addr << 1) | 0x01,
                send_twice=True
            )
            time.sleep(0.05)

            verify = self.send_command_sync(
                address=0xB9,
                command=(short_addr << 1) | 0x01,
                expect_reply=True
            )
            if verify.error == DaliError.RESPONSE:
                assigned.append(DaliDevice(address=short_addr))
                logger.info("Kurzadresse %d zugewiesen (RA=0x%06X)",
                            short_addr, found)

            self.send_command_sync(
                address=0xAB, command=0x00, send_twice=True
            )
            time.sleep(0.05)
            next_address += 1

        self.send_command_sync(address=0xA1, command=0x00, send_twice=True)
        logger.info("Natives Commissioning: %d Geräte adressiert",
                     len(assigned))
        return assigned

    def _find_next_device(self) -> Optional[int]:
        """Iterative binäre Suche nach dem nächsten Gerät."""
        low = 0
        high = 0xFFFFFF

        self._set_search_addr(high)
        time.sleep(0.02)
        resp = self.send_command_sync(
            address=0xA9, command=0x00, expect_reply=True
        )
        if resp.error != DaliError.RESPONSE:
            return None

        while low < high:
            if not self._running:
                return None
            mid = (low + high) // 2
            self._set_search_addr(mid)
            time.sleep(0.02)
            resp = self.send_command_sync(
                address=0xA9, command=0x00, expect_reply=True
            )
            if resp.error == DaliError.RESPONSE:
                high = mid
            else:
                low = mid + 1

        self._set_search_addr(low)
        time.sleep(0.02)
        resp = self.send_command_sync(
            address=0xA9, command=0x00, expect_reply=True
        )
        if resp.error == DaliError.RESPONSE:
            return low
        return None

    def _set_search_addr(self, addr: int):
        """Setze die 24-Bit Suchadresse (SearchAddrH/M/L)."""
        self.send_command_sync(address=0xB1, command=(addr >> 16) & 0xFF)
        time.sleep(0.02)
        self.send_command_sync(address=0xB3, command=(addr >> 8) & 0xFF)
        time.sleep(0.02)
        self.send_command_sync(address=0xB5, command=addr & 0xFF)
        time.sleep(0.02)

    # -------------------------------------------------------------------
    # Feature-Flags
    # -------------------------------------------------------------------
    @property
    def feature_dt6(self) -> bool:
        return self._driver_config.feature_dt6

    @property
    def feature_dt8_tc(self) -> bool:
        return self._driver_config.feature_dt8_tc

    @property
    def feature_dt8_rgb(self) -> bool:
        return self._driver_config.feature_dt8_rgb

    def set_features(self, dt6: bool, dt8_tc: bool, dt8_rgb: bool):
        """Feature-Flags setzen und persistieren."""
        self._driver_config.feature_dt6 = dt6
        self._driver_config.feature_dt8_tc = dt8_tc
        self._driver_config.feature_dt8_rgb = dt8_rgb
        if self._data_dir:
            save_driver_config(self._data_dir, self._driver_config)
        logger.info(
            "Features gesetzt: DT6=%s, DT8_Tc=%s, DT8_RGB=%s",
            dt6, dt8_tc, dt8_rgb
        )

    # -------------------------------------------------------------------
    # DT8: EnableDeviceType (Voraussetzung für alle DT8-Befehle)
    # -------------------------------------------------------------------
    def _enable_device_type(self, device_type: int):
        """Sende EnableDeviceType – muss vor jedem DT-spezifischen Befehl
        gesendet werden (IEC 62386-102, Befehl 0xC1, Daten = Typ).

        Args:
            device_type: 6 für DT6 (LED), 8 für DT8 (Colour)
        """
        # EnableDeviceType: Adressbyte 0xC1, Datenbyte = device_type
        self.send_command_sync(
            address=0xC1, command=device_type & 0xFF, send_twice=True
        )

    # -------------------------------------------------------------------
    # DT8: Tunable White – Farbtemperatur (IEC 62386-209)
    #
    # Farbtemperatur in Mirek (Micro Reciprocal Kelvin):
    #   Mirek = 1.000.000 / Kelvin
    #   2700K warm = 370 Mirek
    #   4000K neutral = 250 Mirek
    #   6500K kalt = 154 Mirek
    #
    # Ablauf:
    #   1. EnableDeviceType(8)
    #   2. SET TEMPORARY COLOUR TEMPERATURE Tc (DTR0 + DTR1 + Befehl 0xE7)
    #   3. ACTIVATE (Befehl 0xE2) – übernimmt die temporären Werte
    # -------------------------------------------------------------------
    def set_colour_temp(self, address: int, mirek: int) -> DaliResponse:
        """Setze die Farbtemperatur eines DT8 Tunable White Geräts.

        Args:
            address: Kurzadresse 0..63, oder 255 für Broadcast
            mirek: Farbtemperatur in Mirek (153..370, typ.)
                   153 = 6500K (kalt), 370 = 2700K (warm)

        Returns:
            DaliResponse
        """
        mirek = max(0, min(65535, mirek))

        # DTR0 setzen (Low-Byte der Farbtemperatur)
        # Befehl 0xA3 = DTR0 (Data Transfer Register 0)
        self.send_command_sync(address=0xA3, command=mirek & 0xFF)

        # DTR1 setzen (High-Byte der Farbtemperatur)
        # Befehl 0xC3 = DTR1
        self.send_command_sync(address=0xC3, command=(mirek >> 8) & 0xFF)

        # EnableDeviceType(8)
        self._enable_device_type(8)

        # SET TEMPORARY COLOUR TEMPERATURE Tc (Befehl 0xE7)
        if address == 255:
            addr_byte = 0xFF
        else:
            addr_byte = ((address & 0x3F) << 1) | 0x01
        self.send_command_sync(address=addr_byte, command=0xE7)

        # ACTIVATE (Befehl 0xE2) – temporäre Werte übernehmen
        self._enable_device_type(8)
        resp = self.send_command_sync(address=addr_byte, command=0xE2)

        self._emit_event('colour_temp', {
            'address': address, 'mirek': mirek
        })
        logger.debug(
            "DT8 Tc: addr=%d mirek=%d (%dK)",
            address, mirek, 1000000 // mirek if mirek > 0 else 0
        )
        return resp

    def set_colour_temp_kelvin(self, address: int, kelvin: int) -> DaliResponse:
        """Convenience: Farbtemperatur in Kelvin setzen.

        Args:
            address: Kurzadresse 0..63, oder 255 für Broadcast
            kelvin: Farbtemperatur in Kelvin (2700..6500, typ.)
        """
        kelvin = max(1, kelvin)
        mirek = 1000000 // kelvin
        return self.set_colour_temp(address, mirek)

    def query_colour_temp(self, address: int) -> DaliResponse:
        """Frage die aktuelle Farbtemperatur eines DT8-Geräts ab.

        Returns:
            DaliResponse mit Mirek-Wert (DTR0 + DTR1) in response
        """
        addr_byte = ((address & 0x3F) << 1) | 0x01

        # DTR0 = 2 (Colour Temperature Tc)
        self.send_command_sync(address=0xA3, command=0x02)

        # EnableDeviceType(8)
        self._enable_device_type(8)

        # QUERY COLOUR VALUE (Befehl 0xFA)
        resp = self.send_command_sync(
            address=addr_byte, command=0xFA, expect_reply=True
        )
        return resp

    # -------------------------------------------------------------------
    # DT8: RGB Farbsteuerung (IEC 62386-209)
    #
    # Ablauf:
    #   1. EnableDeviceType(8)
    #   2. SET TEMPORARY RGB DIMLEVEL für R, G, B
    #      - DTR0 = Kanal-Wert (0..254)
    #      - DTR1 = Kanal-Nr (0=R, 1=G, 2=B, 3=W, 4=A, 5=F)
    #      - Befehl 0xEB = SET TEMPORARY RGB DIMLEVEL
    #   3. ACTIVATE (0xE2)
    # -------------------------------------------------------------------
    def set_rgb(self, address: int, r: int, g: int, b: int) -> DaliResponse:
        """Setze die RGB-Farbe eines DT8-Geräts.

        Args:
            address: Kurzadresse 0..63, oder 255 für Broadcast
            r: Rot 0..254
            g: Gruen 0..254
            b: Blau 0..254

        Returns:
            DaliResponse
        """
        if address == 255:
            addr_byte = 0xFF
        else:
            addr_byte = ((address & 0x3F) << 1) | 0x01

        # Rot setzen (Kanal 0)
        self._set_colour_channel(addr_byte, channel=0, value=r & 0xFF)

        # Gruen setzen (Kanal 1)
        self._set_colour_channel(addr_byte, channel=1, value=g & 0xFF)

        # Blau setzen (Kanal 2)
        self._set_colour_channel(addr_byte, channel=2, value=b & 0xFF)

        # ACTIVATE
        self._enable_device_type(8)
        resp = self.send_command_sync(address=addr_byte, command=0xE2)

        self._emit_event('rgb', {
            'address': address, 'r': r, 'g': g, 'b': b
        })
        logger.debug("DT8 RGB: addr=%d R=%d G=%d B=%d", address, r, g, b)
        return resp

    def _set_colour_channel(self, addr_byte: int, channel: int, value: int):
        """Setze einen einzelnen Farbkanal (DT8 RGBWAF).

        Args:
            addr_byte: DALI-Adressbyte (bereits formatiert)
            channel: 0=R, 1=G, 2=B, 3=W, 4=A, 5=Freecolour
            value: Kanalwert 0..254
        """
        # DTR0 = Kanalwert
        self.send_command_sync(address=0xA3, command=value & 0xFF)

        # DTR1 = Kanalnummer
        self.send_command_sync(address=0xC3, command=channel & 0xFF)

        # EnableDeviceType(8)
        self._enable_device_type(8)

        # SET TEMPORARY RGB DIMLEVEL (Befehl 0xEB)
        self.send_command_sync(address=addr_byte, command=0xEB)

    # -------------------------------------------------------------------
    # DT8: Colour Type Features abfragen
    # -------------------------------------------------------------------
    def query_colour_type_features(self, address: int) -> int:
        """Frage ab, welche Farb-Features ein DT8-Gerät unterstützt.

        Returns:
            Bitmask: Bit 0 = XY, Bit 1 = Tc, Bit 2 = Herstellerspezifisch,
                     Bit 3..7 = Kanalanzahl RGBWAF
            0 wenn kein DT8-Gerät
        """
        addr_byte = ((address & 0x3F) << 1) | 0x01

        self._enable_device_type(8)

        # QUERY COLOUR TYPE FEATURES (Befehl 0xF9)
        resp = self.send_command_sync(
            address=addr_byte, command=0xF9, expect_reply=True
        )
        if resp.error == DaliError.RESPONSE:
            return resp.response
        return 0

    # -------------------------------------------------------------------
    # DT6: LED Gear spezifische Queries (IEC 62386-207)
    # -------------------------------------------------------------------
    def query_operating_mode(self, address: int) -> DaliResponse:
        """Frage den Betriebsmodus eines DT6-Geräts ab."""
        addr_byte = ((address & 0x3F) << 1) | 0x01

        self._enable_device_type(6)

        # QUERY OPERATING MODE (Befehl 0xF4)
        return self.send_command_sync(
            address=addr_byte, command=0xF4, expect_reply=True
        )

    def query_possible_operating_modes(self, address: int) -> DaliResponse:
        """Frage die unterstützten Betriebsmodi ab."""
        addr_byte = ((address & 0x3F) << 1) | 0x01

        self._enable_device_type(6)

        # QUERY POSSIBLE OPERATING MODES (Befehl 0xF5)
        return self.send_command_sync(
            address=addr_byte, command=0xF5, expect_reply=True
        )

    def query_thermal_shutdown(self, address: int) -> DaliResponse:
        """Frage den Thermal-Shutdown-Status ab."""
        addr_byte = ((address & 0x3F) << 1) | 0x01

        self._enable_device_type(6)

        # QUERY FEATURES (Befehl 0xF1) – Bit 1 = Thermal Shutdown
        return self.send_command_sync(
            address=addr_byte, command=0xF1, expect_reply=True
        )

    # -------------------------------------------------------------------
    # -------------------------------------------------------------------
    # Bus-Sniffer (passives Lauschen)
    # -------------------------------------------------------------------
    def sniff_bus(self, duration: float = 10.0) -> list:
        """Lausche passiv auf dem DALI-Bus.

        Args:
            duration: Dauer in Sekunden (default 10)

        Returns:
            Liste von Dicts mit ts, addr, cmd, desc, error
        """
        if not self._driver or not hasattr(self._driver, 'sniff_frames'):
            logger.warning("Treiber unterstützt keinen Sniffer-Modus")
            return []

        logger.info("Bus-Sniffer: Lausche %d Sekunden...", duration)
        raw_frames = self._driver.sniff_frames(duration=duration)

        # Frames mit lesbarer Beschreibung anreichern
        result = []
        for frame in raw_frames:
            desc = _describe_dali_frame(frame['addr'], frame['cmd'])
            entry = {
                'ts': frame['ts'],
                'addr': frame['addr'],
                'addr_hex': f'0x{frame["addr"]:02X}',
                'cmd': frame['cmd'],
                'cmd_hex': f'0x{frame["cmd"]:02X}',
                'desc': desc,
                'error': frame.get('error', False)
            }
            result.append(entry)
            # Auch ins Bus-Log schreiben
            if self._buslog_enabled:
                log_entry = BusLogEntry(
                    timestamp=frame['ts'],
                    direction='SNIFF',
                    address=frame['addr'],
                    command=frame['cmd'],
                    error='SNIFFER_ERROR' if frame.get('error') else '',
                    duration_ms=0.0
                )
                with self._buslog_lock:
                    self._buslog.append(log_entry)

        logger.info("Bus-Sniffer: %d Frames empfangen", len(result))
        return result

    # Erweiterter Bus-Scan mit DT8-Erkennung
    # -------------------------------------------------------------------
    def scan_bus(self) -> dict:
        """Scanne DALI-Bus (Adresse 0..63) mit optionaler DT8-Erkennung."""
        logger.info("Starte Bus-Scan...")
        devices = {}
        for addr in range(64):
            if not self._running:
                break
            if self.query_device_present(addr):
                device = DaliDevice(address=addr)
                level_resp = self.query_actual_level(addr)
                if level_resp.error == DaliError.RESPONSE:
                    device.level = level_resp.response
                type_resp = self.query_device_type(addr)
                if type_resp.error == DaliError.RESPONSE:
                    device.device_type = type_resp.response
                device.groups = self.query_groups(addr)

                # DT8-Features erkennen wenn aktiviert
                if (self.feature_dt8_tc or self.feature_dt8_rgb) \
                        and device.device_type == 8:
                    features = self.query_colour_type_features(addr)
                    device.colour_type = features
                    # Bit 1 = Tc (Tunable White)
                    device.supports_tc = bool(features & 0x02)
                    # Bits 3..7 = Anzahl RGBWAF-Kanaele (>0 = RGB)
                    rgb_channels = (features >> 3) & 0x1F
                    device.supports_rgb = rgb_channels >= 3

                    # Aktuelle Farbtemperatur lesen
                    if device.supports_tc:
                        tc_resp = self.query_colour_temp(addr)
                        if tc_resp.error == DaliError.RESPONSE:
                            device.colour_temp_mirek = tc_resp.response

                devices[addr] = device
                logger.info(
                    "Gerät: Addr %d, Level %d, Typ %d, Gruppen %s, Tc=%s, RGB=%s",
                    addr, device.level, device.device_type, device.groups,
                    device.supports_tc, device.supports_rgb
                )
        with self._devices_lock:
            self._devices = devices
        self._persist_devices()
        self._emit_event('scan_complete', {'count': len(devices)})
        logger.info("Bus-Scan: %d Geräte gefunden", len(devices))
        return devices
