# =============================================================================
# DALI ServUI – Flask-Hauptanwendung
# Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
# Version: 1.0.0 | Deploy: 2026-05-07
#
# Flask + Jinja2 Webanwendung mit REST-API für DALI-Lichtsteuerung.
# Orientiert am daliserver-Ansatz (github.com/onitake/daliserver).
# Unterstützt austauschbare Treiber: Hasseb, MikroE GPIO/FTDI, Dryrun.
# =============================================================================

import json
import logging
import os
import signal
import sys
import threading
import time
from functools import wraps

from flask import (
    Flask, render_template, request, jsonify, session, redirect, url_for,
    Response
)

from app.config import (
    SECRET_KEY, DEBUG, HOST, PORT,
    DEFAULT_LANGUAGE, API_TOKEN, LOG_LEVEL, LOG_FILE,
    VERSION, DATA_DIR, DALI_DRIVER, CORS_ORIGINS
)
from app.dali_service import (
    DaliService, DaliError, DaliResponse,
    load_driver_config, save_driver_config,
    load_dashboards, save_dashboards
)
from app.drivers.base import DaliDriverConfig
from app.drivers.registry import list_drivers
from app.translations import get_translation

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
log_handlers = [logging.StreamHandler(sys.stdout)]
if LOG_FILE:
    log_handlers.append(logging.FileHandler(LOG_FILE))

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
    handlers=log_handlers
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Flask-App
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
    static_folder=os.path.join(os.path.dirname(__file__), 'static')
)
app.secret_key = SECRET_KEY


# ---------------------------------------------------------------------------
# Security-Header und CORS
# CORS-Origins per ENV DALI_CORS_ORIGINS (Komma-getrennt). Leer = keine
# CORS-Header. "*" für offen-für-alle (nicht empfohlen wenn ohne API-Token).
# Security-Header werden auf alle Antworten gesetzt; CSP erlaubt 'unsafe-inline'
# für Scripts und Styles, weil die Templates noch Inline-onclick-Handler
# nutzen (geplante Folge-Aufgabe: addEventListener-Migration).
# ---------------------------------------------------------------------------
_CSP = (
    "default-src 'self'; "
    "img-src 'self' data:; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "connect-src 'self'; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


@app.after_request
def add_security_headers(response):
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('Referrer-Policy', 'same-origin')
    response.headers.setdefault('Content-Security-Policy', _CSP)
    return response


@app.after_request
def add_cors_headers(response):
    if not request.path.startswith('/api/') or not CORS_ORIGINS:
        return response
    origin = request.headers.get('Origin', '')
    if '*' in CORS_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = '*'
    elif origin and origin in CORS_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Vary'] = 'Origin'
    else:
        return response
    response.headers['Access-Control-Allow-Headers'] = \
        'Content-Type, X-API-Token'
    response.headers['Access-Control-Allow-Methods'] = \
        'GET, POST, PUT, DELETE, OPTIONS'
    return response


# ---------------------------------------------------------------------------
# DALI-Service
# ---------------------------------------------------------------------------
os.makedirs(DATA_DIR, exist_ok=True)
dali = DaliService(data_dir=DATA_DIR)

# Commissioning-Lock (verhindert gleichzeitige Ausführung)
_commissioning_lock = threading.Lock()
_commissioning_log_lock = threading.Lock()
_commissioning_running = False
_commissioning_process = None
_commissioning_log = []  # Gepufferte Ausgabezeilen für Seitenwechsel


def _log_append(line: str) -> None:
    with _commissioning_log_lock:
        _commissioning_log.append(line)


def _log_clear() -> None:
    with _commissioning_log_lock:
        _commissioning_log.clear()


def _log_snapshot() -> list:
    with _commissioning_log_lock:
        return list(_commissioning_log)


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------
def get_lang() -> str:
    return session.get('lang', DEFAULT_LANGUAGE)


def api_auth_required(f):
    """API-Token-Pflicht (wenn DALI_API_TOKEN gesetzt).
    Akzeptiert Token im X-API-Token-Header oder als ?token=...-Query-Param.
    Letzteres ist nötig fuer EventSource (SSE), das keine Custom-Header
    senden kann."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if API_TOKEN:
            token = (
                request.headers.get('X-API-Token', '')
                or request.args.get('token', '')
            )
            if token != API_TOKEN:
                return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


def dali_response_to_dict(resp: DaliResponse) -> dict:
    return {
        'error': resp.error.name,
        'error_code': resp.error.value,
        'response': resp.response,
        'success': resp.error.value >= 0
    }


def _build_groups(devices: dict, labels: dict = None) -> dict:
    """Baue Gruppen-Dict aus Geräte-Dict zusammen, Members alphabetisch sortiert."""
    if labels is None:
        labels = {}
    device_labels = labels.get('devices', {})
    groups = {}
    for addr, dev in devices.items():
        for g in dev.groups:
            if g not in groups:
                groups[g] = []
            groups[g].append(dev)
    # Members alphabetisch nach Label sortieren
    for g in groups:
        groups[g].sort(
            key=lambda d: device_labels.get(str(d.address), f'#{d.address:03d}')
        )
    return groups


@app.context_processor
def inject_globals():
    lang = get_lang()
    dashboards_data = load_dashboards(DATA_DIR)
    active_db = session.get('active_dashboard',
                            dashboards_data.get('active', 'default'))
    return {
        't': get_translation(lang),
        'lang': lang,
        'version': VERSION,
        'is_connected': dali.is_connected,
        'is_dryrun': dali.active_driver_id == 'dryrun',
        'active_driver': dali.active_driver_id,
        'feature_dt6': dali.feature_dt6,
        'feature_dt8_tc': dali.feature_dt8_tc,
        'feature_dt8_rgb': dali.feature_dt8_rgb,
        'labels': dali.get_labels(),
        'dashboards': dashboards_data.get('dashboards', {}),
        'active_dashboard': active_db,
        # Wird nur gesetzt, wenn ein API_TOKEN konfiguriert ist – sonst leer.
        # Ohne diesen Token landen alle JS-fetch-Aufrufe in 401, weil
        # api_auth_required denselben Token erwartet.
        'api_token': API_TOKEN,
    }


# ---------------------------------------------------------------------------
# Web-Routes (Seiten)
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    dashboards_data = load_dashboards(DATA_DIR)
    active_id = session.get('active_dashboard',
                            dashboards_data.get('active', 'default'))
    return redirect(url_for('dashboard_page', dashboard_id=active_id))


@app.route('/dashboard/<dashboard_id>')
def dashboard_page(dashboard_id):
    dashboards_data = load_dashboards(DATA_DIR)
    config = dashboards_data['dashboards'].get(dashboard_id)
    if not config:
        return redirect(url_for('dashboard_page', dashboard_id='default'))

    session['active_dashboard'] = dashboard_id
    all_devices = dali.get_devices()
    all_groups = _build_groups(all_devices, dali.get_labels())

    # Items filtern
    filtered_devices = {}
    filtered_groups = {}
    for item in config.get('items', []):
        itype = item.get('type')
        if itype == 'all_devices':
            filtered_devices = dict(all_devices)
        elif itype == 'all_groups':
            filtered_groups = dict(all_groups)
        elif itype == 'device':
            addr = item.get('address')
            if addr in all_devices:
                filtered_devices[addr] = all_devices[addr]
        elif itype == 'group':
            gid = item.get('id')
            if gid in all_groups:
                filtered_groups[gid] = all_groups[gid]

    return render_template(
        'dashboard.html',
        dashboard_id=dashboard_id,
        dashboard_config=config,
        devices=filtered_devices,
        groups=filtered_groups,
        firmware=dali.firmware_version,
        queue_size=dali.queue_size
    )


@app.route('/devices')
def devices_page():
    return render_template('devices.html', devices=dali.get_devices())


@app.route('/groups')
def groups_page():
    return render_template('groups.html',
                           groups=_build_groups(dali.get_devices(),
                                               dali.get_labels()))


@app.route('/discovery')
def discovery_page():
    return render_template('discovery.html', devices=dali.get_devices())


@app.route('/help')
def help_page():
    """Hilfe-Seite mit Anleitung zu allen Features."""
    return render_template('help.html')


@app.route('/healthz')
def healthz():
    return jsonify({'status': 'ok', 'version': VERSION})


@app.route('/settings')
def settings_page():
    drivers = list_drivers()
    config = dali.driver_config
    return render_template(
        'settings.html',
        drivers=drivers,
        active_driver=dali.active_driver_id,
        driver_config=config
    )


@app.route('/buslog')
def buslog_page():
    """Bus-Protokoll – Echtzeit-Ansicht aller DALI-Frames."""
    return render_template('buslog.html')


@app.route('/set-language/<lang>')
def set_language(lang):
    if lang in ('de', 'en'):
        session['lang'] = lang
    return redirect(request.referrer or url_for('index'))


# ---------------------------------------------------------------------------
# REST-API – Server-Sent Events (Echtzeit-Updates)
# ---------------------------------------------------------------------------
@app.route('/api/v1/events')
@api_auth_required
def api_events():
    """SSE-Stream für Echtzeit-Updates (Level, On/Off, Scan, Gruppen).

    Clients erhalten JSON-Events bei jeder Zustandsänderung.
    Event-Typen: level, on, off, group_on, group_off, group_level,
    scan_complete, colour_temp, rgb.
    """
    import queue as queue_mod

    try:
        q = dali.subscribe_events()
    except RuntimeError as exc:
        return jsonify({'error': str(exc)}), 503

    def generate():
        try:
            while True:
                try:
                    event = q.get(timeout=30)
                    yield f"data: {json.dumps(event)}\n\n"
                except queue_mod.Empty:
                    # Keepalive alle 30 Sekunden (verhindert Timeout)
                    yield f": keepalive\n\n"
        except GeneratorExit:
            pass
        finally:
            dali.unsubscribe_events(q)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache',
                             'X-Accel-Buffering': 'no'})


# ---------------------------------------------------------------------------
# REST-API – Status
# ---------------------------------------------------------------------------
@app.route('/api/v1/status')
@api_auth_required
def api_status():
    return jsonify({
        'running': dali.is_running,
        'connected': dali.is_connected,
        'driver': dali.active_driver_id,
        'firmware': dali.firmware_version,
        'devices': len(dali.get_devices()),
        'queue_size': dali.queue_size,
        'version': VERSION
    })


# ---------------------------------------------------------------------------
# REST-API – Treiber-Verwaltung
# ---------------------------------------------------------------------------
@app.route('/api/v1/drivers')
@api_auth_required
def api_drivers():
    """Liste aller verfügbaren Treiber mit Infos."""
    drivers = list_drivers()
    result = []
    for d in drivers:
        result.append({
            'id': d.id,
            'name': d.name,
            'description_de': d.description_de,
            'description_en': d.description_en,
            'requires': d.requires,
            'available': d.available,
            'config_fields': d.config_fields,
            'active': d.id == dali.active_driver_id
        })
    return jsonify(result)


@app.route('/api/v1/drivers/switch', methods=['POST'])
@api_auth_required
def api_switch_driver():
    """Treiber wechseln. Body: {"driver_id": "...", ...config_fields...}"""
    data = request.get_json(silent=True) or {}
    driver_id = data.get('driver_id', '')

    if not driver_id:
        return jsonify({'error': 'driver_id required'}), 400

    # Konfiguration aus Request übernehmen
    config = DaliDriverConfig(driver_id=driver_id)
    for key in ('gpio_tx_pin', 'gpio_rx_pin', 'ftdi_tx_pin', 'ftdi_rx_pin'):
        if key in data:
            setattr(config, key, int(data[key]))
    for key in ('gpio_tx_inverted', 'ftdi_tx_inverted'):
        if key in data:
            setattr(config, key, bool(data[key]))
    for key in ('gpio_chip', 'ftdi_url'):
        if key in data:
            setattr(config, key, str(data[key]))

    error = dali.switch_driver(driver_id, config)
    return jsonify({
        'success': error == DaliError.SUCCESS,
        'driver': dali.active_driver_id,
        'error': error.name
    })


@app.route('/api/v1/drivers/commission-status')
@api_auth_required
def api_commission_status():
    """Prüfe ob ein Commissioning gerade läuft. Gibt auch den bisherigen Output zurück."""
    return jsonify({
        'running': _commissioning_running,
        'log': _log_snapshot()
    })


@app.route('/api/v1/drivers/commission-stream')
@api_auth_required
def api_commission_stream():
    """Commissioning via python-dali mit Live-Output (SSE Stream)."""
    global _commissioning_running, _commissioning_process
    from flask import Response

    # Gleichzeitige Ausführung verhindern
    if not _commissioning_lock.acquire(blocking=False):
        return jsonify({'error': 'Commissioning läuft bereits'}), 409

    def _log_and_yield(line):
        """Zeile an SSE senden und im Buffer speichern."""
        _log_append(line)
        return f"data: {line}\n\n"

    def generate():
        global _commissioning_running, _commissioning_process
        import subprocess as sp

        _commissioning_running = True
        _log_clear()

        try:
            # Treiber stoppen (USB freigeben für python-dali Subprocess)
            if dali.is_running:
                dali.stop()
                yield _log_and_yield('Treiber gestoppt – USB freigegeben')
                # Warten bis USB-Device tatsächlich freigegeben ist
                time.sleep(1.5)

            script = '''
import time, sys
from dali.driver.hasseb import SyncHassebDALIUSBDriver as Drv
from dali.gear.general import Reset, DTR0, QueryControlGearPresent
from dali.address import Broadcast, Short
from dali.sequences import Commissioning, Initialise, Terminate, SetShortAddress

drv = Drv()
print("Hasseb geöffnet", flush=True)

print("1. Alle Kurzadressen löschen...", flush=True)
drv.send(Terminate()); time.sleep(0.1)
drv.send(Initialise(broadcast=True)); time.sleep(0.1)
drv.send(Initialise(broadcast=True)); time.sleep(0.3)
drv.send(DTR0(255)); time.sleep(0.05)
drv.send(SetShortAddress(Broadcast())); time.sleep(0.1)
drv.send(SetShortAddress(Broadcast())); time.sleep(0.1)
drv.send(Terminate()); time.sleep(0.5)

print("   Verify: Prüfe alle Adressen...", flush=True)
still_there = 0
for addr in range(64):
    resp = drv.send(QueryControlGearPresent(Short(addr)))
    if resp and resp.raw_value is not None:
        still_there += 1
if still_there > 0:
    print(f"   WARNUNG: {still_there} Adressen antworten noch", flush=True)
else:
    print("   Alle Adressen gelöscht.", flush=True)

print("", flush=True)
print("2. Commissioning...", flush=True)
def on_progress(p):
    print(f"   {p}", flush=True)

drv.run_sequence(Commissioning(), progress_cb=on_progress)

print("", flush=True)
print("3. Bus-Scan...", flush=True)
found = 0
for addr in range(64):
    resp = drv.send(QueryControlGearPresent(Short(addr)))
    if resp and resp.raw_value is not None:
        found += 1
        print(f"   Addr {addr}: vorhanden", flush=True)

print(f"", flush=True)
print(f"TOTAL={found} Geräte gefunden", flush=True)
try: drv.close()
except: pass
'''

            try:
                proc = sp.Popen(
                    [sys.executable, '-u', '-c', script],
                    stdout=sp.PIPE, stderr=sp.STDOUT,
                    text=True, bufsize=1
                )
                _commissioning_process = proc
                for line in proc.stdout:
                    line = line.rstrip()
                    if line:
                        yield _log_and_yield(line)
                proc.wait()
                _commissioning_process = None
            except Exception as e:
                _commissioning_process = None
                yield _log_and_yield(f'FEHLER: {e}')

            # Treiber wieder starten
            yield _log_and_yield('Treiber wird neu gestartet...')
            time.sleep(1.5)
            error = dali.start()
            if error == DaliError.SUCCESS:
                yield _log_and_yield('Treiber gestartet')
                # Bus-Scan ausführen damit Geräte in der UI sichtbar sind
                yield _log_and_yield('Bus-Scan wird ausgeführt...')
                devices = dali.scan_bus()
                yield _log_and_yield(f'Bus-Scan: {len(devices)} Geräte gefunden')
            else:
                yield _log_and_yield(
                    f'WARNUNG: Treiber konnte nicht gestartet werden ({error.name})')

            yield f"data: [DONE]\n\n"

        finally:
            _commissioning_running = False
            _commissioning_lock.release()

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/v1/drivers/stop', methods=['POST'])
@api_auth_required
def api_stop_driver():
    """Treiber stoppen (USB freigeben für CLI-Tools)."""
    if dali.is_running:
        dali.stop()
    return jsonify({
        'success': True,
        'running': dali.is_running,
        'message': 'Treiber gestoppt – USB freigegeben für CLI-Commissioning'
    })


@app.route('/api/v1/drivers/start', methods=['POST'])
@api_auth_required
def api_start_driver():
    """Treiber (wieder) starten."""
    if dali.is_running:
        return jsonify({'success': True, 'running': True, 'message': 'Läuft bereits'})
    error = dali.start()
    return jsonify({
        'success': error == DaliError.SUCCESS,
        'running': dali.is_running,
        'error': error.name
    })


@app.route('/api/v1/drivers/config')
@api_auth_required
def api_driver_config():
    """Aktuelle Treiber-Konfiguration abfragen."""
    config = dali.driver_config
    return jsonify({
        'driver_id': config.driver_id,
        'gpio_tx_pin': config.gpio_tx_pin,
        'gpio_rx_pin': config.gpio_rx_pin,
        'gpio_tx_inverted': config.gpio_tx_inverted,
        'gpio_chip': config.gpio_chip,
        'ftdi_url': config.ftdi_url,
        'ftdi_tx_pin': config.ftdi_tx_pin,
        'ftdi_rx_pin': config.ftdi_rx_pin,
        'ftdi_tx_inverted': config.ftdi_tx_inverted,
    })


# ---------------------------------------------------------------------------
# REST-API – Geräte-Steuerung
# ---------------------------------------------------------------------------
@app.route('/api/v1/devices')
@api_auth_required
def api_devices():
    devices = dali.get_devices()
    result = {}
    for addr, dev in devices.items():
        result[str(addr)] = {
            'address': dev.address, 'level': dev.level,
            'device_type': dev.device_type, 'groups': dev.groups,
            'present': dev.present
        }
    return jsonify(result)


@app.route('/api/v1/devices/<int:address>/on', methods=['POST'])
@api_auth_required
def api_device_on(address):
    return jsonify(dali_response_to_dict(dali.turn_on(address)))


@app.route('/api/v1/devices/<int:address>/off', methods=['POST'])
@api_auth_required
def api_device_off(address):
    return jsonify(dali_response_to_dict(dali.turn_off(address)))


@app.route('/api/v1/devices/<int:address>/level', methods=['POST'])
@api_auth_required
def api_device_level(address):
    data = request.get_json(silent=True) or {}
    level = data.get('level', 0)
    if not isinstance(level, int) or level < 0 or level > 254:
        return jsonify({'error': 'level must be 0..254'}), 400
    return jsonify(dali_response_to_dict(dali.set_level(address, level)))


@app.route('/api/v1/devices/<int:address>/status')
@api_auth_required
def api_device_status(address):
    return jsonify(dali_response_to_dict(dali.query_status(address)))


@app.route('/api/v1/devices/<int:address>/level')
@api_auth_required
def api_device_get_level(address):
    return jsonify(dali_response_to_dict(dali.query_actual_level(address)))


# ---------------------------------------------------------------------------
# REST-API – Broadcast
# ---------------------------------------------------------------------------
@app.route('/api/v1/broadcast/on', methods=['POST'])
@api_auth_required
def api_broadcast_on():
    return jsonify(dali_response_to_dict(dali.turn_on(255)))


@app.route('/api/v1/broadcast/off', methods=['POST'])
@api_auth_required
def api_broadcast_off():
    return jsonify(dali_response_to_dict(dali.turn_off(255)))


@app.route('/api/v1/broadcast/level', methods=['POST'])
@api_auth_required
def api_broadcast_level():
    data = request.get_json(silent=True) or {}
    level = data.get('level', 0)
    if not isinstance(level, int) or level < 0 or level > 254:
        return jsonify({'error': 'level must be 0..254'}), 400
    return jsonify(dali_response_to_dict(dali.set_level(255, level)))


# ---------------------------------------------------------------------------
# REST-API – Gruppen
# ---------------------------------------------------------------------------
@app.route('/api/v1/groups')
@api_auth_required
def api_groups():
    """Alle Gruppen mit Namen, Mitgliedern und Level."""
    devices = dali.get_devices()
    labels = dali.get_labels()
    groups = {}
    for addr, dev in devices.items():
        for g in dev.groups:
            gid = str(g)
            if gid not in groups:
                groups[gid] = {
                    'id': g,
                    'name': labels['groups'].get(gid, ''),
                    'members': []
                }
            groups[gid]['members'].append({
                'address': dev.address,
                'name': labels['devices'].get(str(addr), ''),
                'level': dev.level,
                'present': dev.present
            })
    return jsonify(groups)


@app.route('/api/v1/groups/<int:group>/on', methods=['POST'])
@api_auth_required
def api_group_on(group):
    if group < 0 or group > 15:
        return jsonify({'error': 'group must be 0..15'}), 400
    return jsonify(dali_response_to_dict(dali.group_on(group)))


@app.route('/api/v1/groups/<int:group>/off', methods=['POST'])
@api_auth_required
def api_group_off(group):
    if group < 0 or group > 15:
        return jsonify({'error': 'group must be 0..15'}), 400
    return jsonify(dali_response_to_dict(dali.group_off(group)))


@app.route('/api/v1/groups/<int:group>/level', methods=['POST'])
@api_auth_required
def api_group_level(group):
    if group < 0 or group > 15:
        return jsonify({'error': 'group must be 0..15'}), 400
    data = request.get_json(silent=True) or {}
    level = data.get('level', 0)
    if not isinstance(level, int) or level < 0 or level > 254:
        return jsonify({'error': 'level must be 0..254'}), 400
    return jsonify(dali_response_to_dict(dali.group_level(group, level)))


# ---------------------------------------------------------------------------
# REST-API – Discovery
# ---------------------------------------------------------------------------
@app.route('/api/v1/scan', methods=['POST'])
@api_auth_required
def api_scan():
    threading.Thread(target=dali.scan_bus, name="bus-scan", daemon=True).start()
    return jsonify({'status': 'scan_started'})


@app.route('/api/v1/commission', methods=['POST'])
@api_auth_required
def api_commission():
    data = request.get_json(silent=True) or {}
    broadcast = data.get('broadcast', True)

    def do_commission():
        dali.initialize_bus(broadcast=broadcast)
        dali.scan_bus()

    threading.Thread(target=do_commission, name="commissioning", daemon=True).start()
    return jsonify({'status': 'commissioning_started'})


@app.route('/api/v1/sniff', methods=['POST'])
@api_auth_required
def api_sniff():
    """Bus-Sniffer starten. Body: {"duration": 10}"""
    data = request.get_json(silent=True) or {}
    try:
        raw = float(data.get('duration', 10))
    except (TypeError, ValueError):
        return jsonify({'error': 'duration must be a number'}), 400
    duration = max(0.5, min(raw, 60))
    frames = dali.sniff_bus(duration=duration)
    return jsonify({'frames': frames, 'count': len(frames)})


@app.route('/api/v1/reset-addresses', methods=['POST'])
@api_auth_required
def api_reset_addresses():
    """Alle Kurzadressen löschen (DTR=0xFF + Store)."""
    dali.reset_addresses()
    return jsonify({'status': 'addresses_reset'})


@app.route('/api/v1/factory-reset', methods=['POST'])
@api_auth_required
def api_factory_reset():
    """Vollständiger DALI Factory Reset."""
    dali.reset_bus_factory()
    return jsonify({'status': 'factory_reset_done'})


# ---------------------------------------------------------------------------
# REST-API – Labels (Geräte- und Gruppennamen)
# ---------------------------------------------------------------------------
@app.route('/api/v1/labels')
@api_auth_required
def api_labels():
    """Alle Labels abfragen."""
    return jsonify(dali.get_labels())


_LABEL_MAX_LEN = 100


@app.route('/api/v1/labels/device/<int:address>', methods=['POST'])
@api_auth_required
def api_set_device_label(address):
    """Gerätename setzen. Body: {"name": "Schreibtisch"}"""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()[:_LABEL_MAX_LEN]
    dali.set_device_label(address, name)
    return jsonify({'success': True, 'address': address, 'name': name})


@app.route('/api/v1/labels/group/<int:group>', methods=['POST'])
@api_auth_required
def api_set_group_label(group):
    """Gruppenname setzen. Body: {"name": "Buero"}"""
    data = request.get_json(silent=True) or {}
    name = str(data.get('name', '')).strip()[:_LABEL_MAX_LEN]
    dali.set_group_label(group, name)
    return jsonify({'success': True, 'group': group, 'name': name})


# ---------------------------------------------------------------------------
# REST-API – Gruppenzuweisung
# ---------------------------------------------------------------------------
@app.route('/api/v1/devices/<int:address>/groups', methods=['POST'])
@api_auth_required
def api_add_to_group(address):
    """Gerät einer Gruppe hinzufügen. Body: {"group": 0}"""
    data = request.get_json(silent=True) or {}
    group = int(data.get('group', -1))
    if group < 0 or group > 15:
        return jsonify({'error': 'group must be 0..15'}), 400
    resp = dali.add_to_group(address, group)
    return jsonify(dali_response_to_dict(resp))


@app.route('/api/v1/devices/<int:address>/groups', methods=['DELETE'])
@api_auth_required
def api_remove_from_group(address):
    """Gerät aus einer Gruppe entfernen. Body: {"group": 0}"""
    data = request.get_json(silent=True) or {}
    group = int(data.get('group', -1))
    if group < 0 or group > 15:
        return jsonify({'error': 'group must be 0..15'}), 400
    resp = dali.remove_from_group(address, group)
    return jsonify(dali_response_to_dict(resp))


# ---------------------------------------------------------------------------
# REST-API – Feature-Toggles
# ---------------------------------------------------------------------------
@app.route('/api/v1/features')
@api_auth_required
def api_features():
    """Aktuelle Feature-Flags abfragen."""
    return jsonify({
        'dt6': dali.feature_dt6,
        'dt8_tc': dali.feature_dt8_tc,
        'dt8_rgb': dali.feature_dt8_rgb
    })


@app.route('/api/v1/features', methods=['POST'])
@api_auth_required
def api_set_features():
    """Feature-Flags setzen. Body: {"dt6": bool, "dt8_tc": bool, "dt8_rgb": bool}"""
    data = request.get_json(silent=True) or {}
    dali.set_features(
        dt6=data.get('dt6', dali.feature_dt6),
        dt8_tc=data.get('dt8_tc', dali.feature_dt8_tc),
        dt8_rgb=data.get('dt8_rgb', dali.feature_dt8_rgb)
    )
    return jsonify({
        'success': True,
        'dt6': dali.feature_dt6,
        'dt8_tc': dali.feature_dt8_tc,
        'dt8_rgb': dali.feature_dt8_rgb
    })


# ---------------------------------------------------------------------------
# REST-API – Dashboards
# ---------------------------------------------------------------------------
def _slugify(name: str) -> str:
    """Erzeuge eine URL-sichere ID aus einem Dashboard-Namen."""
    import re
    s = name.lower().strip()
    for old, new in [('ä', 'ae'), ('ö', 'oe'), ('ü', 'ue'), ('ß', 'ss'),
                     (' ', '-')]:
        s = s.replace(old, new)
    s = re.sub(r'[^a-z0-9-]', '', s)
    return s or 'dashboard'


_VALID_ITEM_TYPES = {'all_devices', 'all_groups', 'device', 'group'}
_DASHBOARD_NAME_MAX_LEN = 80


def _sanitize_items(raw_items) -> list:
    """Validiere und säubere Dashboard-Items. Verwirft unbekannte Typen
    und beschränkt Adressen/Gruppen-IDs auf gültige Bereiche."""
    if not isinstance(raw_items, list):
        return [{'type': 'all_devices'}]
    cleaned = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        t = it.get('type')
        if t not in _VALID_ITEM_TYPES:
            continue
        if t == 'device':
            try:
                addr = int(it.get('address', -1))
            except (TypeError, ValueError):
                continue
            if 0 <= addr <= 63:
                cleaned.append({'type': 'device', 'address': addr})
        elif t == 'group':
            try:
                gid = int(it.get('id', -1))
            except (TypeError, ValueError):
                continue
            if 0 <= gid <= 15:
                cleaned.append({'type': 'group', 'id': gid})
        else:
            cleaned.append({'type': t})
    return cleaned or [{'type': 'all_devices'}]


@app.route('/api/v1/dashboards')
@api_auth_required
def api_dashboards():
    """Alle Dashboards auflisten."""
    data = load_dashboards(DATA_DIR)
    return jsonify(data)


@app.route('/api/v1/dashboards/<dashboard_id>')
@api_auth_required
def api_dashboard_get(dashboard_id):
    """Einzelnes Dashboard abrufen."""
    data = load_dashboards(DATA_DIR)
    cfg = data['dashboards'].get(dashboard_id)
    if not cfg:
        return jsonify({'error': 'Dashboard not found'}), 404
    return jsonify({'id': dashboard_id, **cfg})


@app.route('/api/v1/dashboards', methods=['POST'])
@api_auth_required
def api_dashboard_create():
    """Neues Dashboard erstellen."""
    body = request.get_json(silent=True) or {}
    name = str(body.get('name', '')).strip()[:_DASHBOARD_NAME_MAX_LEN]
    if not name:
        return jsonify({'error': 'name required'}), 400

    data = load_dashboards(DATA_DIR)
    slug = _slugify(name)
    base_slug = slug
    counter = 2
    while slug in data['dashboards']:
        slug = f'{base_slug}-{counter}'
        counter += 1

    max_order = max((d.get('order', 0)
                     for d in data['dashboards'].values()), default=0)
    data['dashboards'][slug] = {
        'name': name,
        'order': max_order + 1,
        'show_status_cards': bool(body.get('show_status_cards', False)),
        'show_broadcast': bool(body.get('show_broadcast', False)),
        'items': _sanitize_items(body.get('items'))
    }
    save_dashboards(DATA_DIR, data)
    return jsonify({'success': True, 'id': slug,
                    **data['dashboards'][slug]}), 201


@app.route('/api/v1/dashboards/<dashboard_id>', methods=['PUT'])
@api_auth_required
def api_dashboard_update(dashboard_id):
    """Dashboard aktualisieren."""
    data = load_dashboards(DATA_DIR)
    if dashboard_id not in data['dashboards']:
        return jsonify({'error': 'Dashboard not found'}), 404

    body = request.get_json(silent=True) or {}
    cfg = data['dashboards'][dashboard_id]
    if 'name' in body:
        cfg['name'] = str(body['name']).strip()[:_DASHBOARD_NAME_MAX_LEN]
    if 'show_status_cards' in body:
        cfg['show_status_cards'] = bool(body['show_status_cards'])
    if 'show_broadcast' in body:
        cfg['show_broadcast'] = bool(body['show_broadcast'])
    if 'items' in body:
        cfg['items'] = _sanitize_items(body['items'])

    save_dashboards(DATA_DIR, data)
    return jsonify({'success': True, 'id': dashboard_id, **cfg})


@app.route('/api/v1/dashboards/<dashboard_id>', methods=['DELETE'])
@api_auth_required
def api_dashboard_delete(dashboard_id):
    """Dashboard löschen (default ist geschützt)."""
    if dashboard_id == 'default':
        return jsonify({'error': 'Cannot delete default dashboard'}), 400

    data = load_dashboards(DATA_DIR)
    if dashboard_id not in data['dashboards']:
        return jsonify({'error': 'Dashboard not found'}), 404

    del data['dashboards'][dashboard_id]
    if data.get('active') == dashboard_id:
        data['active'] = 'default'
    save_dashboards(DATA_DIR, data)
    return jsonify({'success': True})


# ---------------------------------------------------------------------------
# REST-API – DT8 Colour (Tunable White + RGB)
# ---------------------------------------------------------------------------
@app.route('/api/v1/devices/<int:address>/colour-temp', methods=['POST'])
@api_auth_required
def api_device_colour_temp(address):
    """Farbtemperatur setzen. Body: {"mirek": 153..370} oder {"kelvin": 2700..6500}"""
    if not dali.feature_dt8_tc:
        return jsonify({'error': 'DT8 Tunable White not enabled'}), 400
    data = request.get_json(silent=True) or {}
    if 'kelvin' in data:
        kelvin = int(data['kelvin'])
        if kelvin < 1000 or kelvin > 10000:
            return jsonify({'error': 'kelvin must be 1000..10000'}), 400
        resp = dali.set_colour_temp_kelvin(address, kelvin)
    elif 'mirek' in data:
        mirek = int(data['mirek'])
        if mirek < 1 or mirek > 65535:
            return jsonify({'error': 'mirek must be 1..65535'}), 400
        resp = dali.set_colour_temp(address, mirek)
    else:
        return jsonify({'error': 'mirek or kelvin required'}), 400
    return jsonify(dali_response_to_dict(resp))


@app.route('/api/v1/devices/<int:address>/rgb', methods=['POST'])
@api_auth_required
def api_device_rgb(address):
    """RGB-Farbe setzen. Body: {"r": 0..254, "g": 0..254, "b": 0..254}"""
    if not dali.feature_dt8_rgb:
        return jsonify({'error': 'DT8 RGB not enabled'}), 400
    data = request.get_json(silent=True) or {}
    r = int(data.get('r', 0))
    g = int(data.get('g', 0))
    b = int(data.get('b', 0))
    if not all(0 <= v <= 254 for v in (r, g, b)):
        return jsonify({'error': 'r, g, b must be 0..254'}), 400
    resp = dali.set_rgb(address, r, g, b)
    return jsonify(dali_response_to_dict(resp))


@app.route('/api/v1/broadcast/colour-temp', methods=['POST'])
@api_auth_required
def api_broadcast_colour_temp():
    """Broadcast: Farbtemperatur setzen."""
    if not dali.feature_dt8_tc:
        return jsonify({'error': 'DT8 Tunable White not enabled'}), 400
    data = request.get_json(silent=True) or {}
    if 'kelvin' in data:
        resp = dali.set_colour_temp_kelvin(255, int(data['kelvin']))
    elif 'mirek' in data:
        resp = dali.set_colour_temp(255, int(data['mirek']))
    else:
        return jsonify({'error': 'mirek or kelvin required'}), 400
    return jsonify(dali_response_to_dict(resp))


@app.route('/api/v1/broadcast/rgb', methods=['POST'])
@api_auth_required
def api_broadcast_rgb():
    """Broadcast: RGB-Farbe setzen."""
    if not dali.feature_dt8_rgb:
        return jsonify({'error': 'DT8 RGB not enabled'}), 400
    data = request.get_json(silent=True) or {}
    r, g, b = int(data.get('r', 0)), int(data.get('g', 0)), int(data.get('b', 0))
    resp = dali.set_rgb(255, r, g, b)
    return jsonify(dali_response_to_dict(resp))


# ---------------------------------------------------------------------------
# REST-API – Bus-Protokoll
# ---------------------------------------------------------------------------
@app.route('/api/v1/buslog')
@api_auth_required
def api_buslog():
    """Bus-Protokoll abrufen. Query-Params: limit (default 100), since (Timestamp)."""
    limit = request.args.get('limit', 100, type=int)
    since = request.args.get('since', 0.0, type=float)
    entries = dali.get_buslog(limit=limit, since=since)
    return jsonify({'entries': entries, 'enabled': dali.buslog_enabled})


@app.route('/api/v1/buslog', methods=['DELETE'])
@api_auth_required
def api_buslog_clear():
    """Bus-Protokoll löschen."""
    dali.clear_buslog()
    return jsonify({'success': True})


@app.route('/api/v1/buslog/toggle', methods=['POST'])
@api_auth_required
def api_buslog_toggle():
    """Bus-Protokoll aktivieren/deaktivieren."""
    data = request.get_json(silent=True) or {}
    dali.buslog_enabled = data.get('enabled', not dali.buslog_enabled)
    return jsonify({'enabled': dali.buslog_enabled})


# ---------------------------------------------------------------------------
# REST-API – Raw DALI-Befehl
# ---------------------------------------------------------------------------
@app.route('/api/v1/raw', methods=['POST'])
@api_auth_required
def api_raw():
    data = request.get_json(silent=True) or {}
    address = data.get('address', 0)
    command = data.get('command', 0)
    expect_reply = data.get('expect_reply', False)
    if not (0 <= address <= 255 and 0 <= command <= 255):
        return jsonify({'error': 'address and command must be 0..255'}), 400
    resp = dali.send_command_sync(
        address=address, command=command, expect_reply=expect_reply
    )
    return jsonify(dali_response_to_dict(resp))


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------
def shutdown_handler(signum, frame):
    logger.info("Shutdown-Signal (%s)", signum)
    dali.stop()
    sys.exit(0)


# ---------------------------------------------------------------------------
# App-Factory
# ---------------------------------------------------------------------------
def create_app():
    """App-Factory für Gunicorn und Tests."""
    driver_id = DALI_DRIVER or ''
    error = dali.start(driver_id=driver_id)
    if error != DaliError.SUCCESS:
        logger.warning("DALI-Service Start-Fehler: %s", error.name)
    # Signal-Handler in der Factory registrieren, damit auch der
    # Gunicorn-Worker (nicht nur __main__) sauber herunterfaehrt.
    try:
        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)
    except ValueError:
        # Signale lassen sich nur im Haupt-Thread setzen; in manchen
        # Test-Umgebungen ist das nicht der Fall.
        pass
    return app


if __name__ == '__main__':
    application = create_app()
    logger.info(
        "DALI ServUI v%s auf %s:%d (Treiber: %s)",
        VERSION, HOST, PORT, dali.active_driver_id
    )
    application.run(host=HOST, port=PORT, debug=DEBUG)
