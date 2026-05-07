/* ===========================================================================
   DALI ServUI – Frontend-JavaScript
   Autor: c42u | Co-Autor: ClaudeCode | Lizenz: GPLv3
   Version: 1.0.0 | Deploy: 2026-05-07
   =========================================================================== */

// ---------------------------------------------------------------------------
// Globaler Aktivitäts-Indikator
// ---------------------------------------------------------------------------
let _activeRequests = 0;

function _showActivity() {
    _activeRequests++;
    const el = document.getElementById('activity-indicator');
    if (el) el.style.display = '';
}

function _hideActivity() {
    _activeRequests = Math.max(0, _activeRequests - 1);
    if (_activeRequests === 0) {
        const el = document.getElementById('activity-indicator');
        if (el) el.style.display = 'none';
    }
}

// ---------------------------------------------------------------------------
// API-Hilfsfunktionen
// ---------------------------------------------------------------------------

/**
 * Sende einen API-Request und gib die JSON-Antwort zurück.
 * Zeigt automatisch den globalen Aktivitäts-Indikator.
 * @param {string} endpoint - API-Pfad (z.B. '/api/v1/status')
 * @param {object} options - Fetch-Optionen (method, body, etc.)
 * @returns {Promise<object>} JSON-Antwort
 */
// API-Token aus dem Meta-Tag in base.html. Bleibt leer, wenn DALI_API_TOKEN
// serverseitig nicht gesetzt ist; dann wird auch kein X-API-Token-Header
// mitgesendet. Auch global verfuegbar als window.API_TOKEN, damit
// Inline-Templates (z.B. discovery.html EventSource) ihn als Query-Param
// anhaengen koennen.
const API_TOKEN = (() => {
    const m = document.querySelector('meta[name="x-api-token"]');
    return m ? (m.getAttribute('content') || '') : '';
})();
window.API_TOKEN = API_TOKEN;

async function apiRequest(endpoint, options = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (API_TOKEN) {
        headers['X-API-Token'] = API_TOKEN;
    }
    const config = { ...options, headers: { ...headers, ...(options.headers || {}) } };

    _showActivity();
    try {
        const response = await fetch(endpoint, config);
        return await response.json();
    } catch (error) {
        console.error('API-Fehler:', error);
        return { error: error.message, success: false };
    } finally {
        _hideActivity();
    }
}

/**
 * POST-Request an die API.
 * @param {string} endpoint - API-Pfad
 * @param {object} data - Request-Body als Objekt
 * @returns {Promise<object>} JSON-Antwort
 */
async function apiPost(endpoint, data = {}) {
    return apiRequest(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

// ---------------------------------------------------------------------------
// Geräte-Steuerung
// ---------------------------------------------------------------------------

/** Einzelnes Gerät einschalten */
async function deviceOn(address) {
    const result = await apiPost(`/api/v1/devices/${address}/on`);
    if (result.success) {
        updateDeviceIndicator(address, true);
        updateDeviceRow(address, 254);
    }
}

/** Einzelnes Gerät ausschalten */
async function deviceOff(address) {
    const result = await apiPost(`/api/v1/devices/${address}/off`);
    if (result.success) {
        updateDeviceIndicator(address, false);
        updateDeviceRow(address, 0);
    }
}

/** Helligkeit eines Geräts setzen */
async function deviceLevel(address, level) {
    level = parseInt(level);
    const result = await apiPost(`/api/v1/devices/${address}/level`, { level });
    if (result.success) {
        updateDeviceIndicator(address, level > 0);
        updateLevelBar(address, level);
        updateDeviceRow(address, level);
    }
}

// ---------------------------------------------------------------------------
// Broadcast-Steuerung
// ---------------------------------------------------------------------------

/** Alle Geräte einschalten */
async function broadcastOn() {
    await apiPost('/api/v1/broadcast/on');
    document.querySelectorAll('.device-indicator').forEach(el => {
        el.classList.remove('off');
        el.classList.add('on');
    });
}

/** Alle Geräte ausschalten */
async function broadcastOff() {
    await apiPost('/api/v1/broadcast/off');
    document.querySelectorAll('.device-indicator').forEach(el => {
        el.classList.remove('on');
        el.classList.add('off');
    });
}

/** Broadcast-Helligkeit setzen */
async function broadcastLevel() {
    const slider = document.getElementById('broadcast-level');
    if (slider) {
        const level = parseInt(slider.value);
        await apiPost('/api/v1/broadcast/level', { level });
    }
}

// ---------------------------------------------------------------------------
// Gruppen-Steuerung
// ---------------------------------------------------------------------------

/** Gruppe ein-/ausschalten (Toggle) */
async function groupToggle(group, btn) {
    const isOn = btn.dataset.on === '1';
    if (isOn) {
        await apiPost(`/api/v1/groups/${group}/off`);
    } else {
        await apiPost(`/api/v1/groups/${group}/on`);
    }
    // UI aktualisieren
    const card = btn.closest('.group-card');
    if (card) {
        const nowOn = !isOn;
        btn.dataset.on = nowOn ? '1' : '0';
        btn.textContent = nowOn ? (btn.dataset.labelOff || 'Aus') : (btn.dataset.labelOn || 'Ein');
        btn.className = 'btn ' + (nowOn ? 'btn-off' : 'btn-on') + ' group-toggle-btn';
        card.classList.remove('group-on', 'group-warning', 'group-off');
        card.classList.add(nowOn ? 'group-on' : 'group-off');
        card.querySelectorAll('.member-badge:not(.member-warning)').forEach(b => {
            b.classList.toggle('member-on', nowOn);
            b.classList.toggle('member-off', !nowOn);
        });
    }
}

/** Gruppe einschalten (für API/Kompatibilität) */
async function groupOn(group) {
    await apiPost(`/api/v1/groups/${group}/on`);
}

/** Gruppe ausschalten (für API/Kompatibilität) */
async function groupOff(group) {
    await apiPost(`/api/v1/groups/${group}/off`);
}

/** Gruppen-Helligkeit setzen */
async function groupLevel(group, level) {
    level = parseInt(level);
    await apiPost(`/api/v1/groups/${group}/level`, { level });
}

// ---------------------------------------------------------------------------
// DT8: Farbtemperatur (Tunable White)
// ---------------------------------------------------------------------------

/** Farbtemperatur eines Geräts setzen (Mirek-Wert) */
async function deviceColourTemp(address, mirek) {
    mirek = parseInt(mirek);
    await apiPost(`/api/v1/devices/${address}/colour-temp`, { mirek });
}

/** Broadcast-Farbtemperatur setzen */
async function broadcastColourTemp() {
    const slider = document.getElementById('broadcast-tc');
    if (slider) {
        const mirek = parseInt(slider.value);
        await apiPost('/api/v1/broadcast/colour-temp', { mirek });
    }
}

/** Tc-Slider-Label aktualisieren (Mirek → Kelvin) */
function updateTcLabel(slider, labelId) {
    const label = document.getElementById(labelId);
    if (label) {
        const mirek = parseInt(slider.value);
        const kelvin = Math.round(1000000 / mirek);
        label.textContent = kelvin + 'K';
    }
}

// ---------------------------------------------------------------------------
// DT8: RGB Farbsteuerung
// ---------------------------------------------------------------------------

/** RGB eines Geräts setzen (aus Colour-Picker) */
async function deviceRgbFromPicker(address, hexColour) {
    const rgb = hexToRgb(hexColour);
    if (rgb) {
        await apiPost(`/api/v1/devices/${address}/rgb`, rgb);
    }
}

/** Broadcast-RGB setzen (aus Colour-Picker) */
async function broadcastRgbFromPicker(hexColour) {
    const rgb = hexToRgb(hexColour);
    const label = document.getElementById('broadcast-rgb-val');
    if (label) label.textContent = hexColour;
    if (rgb) {
        await apiPost('/api/v1/broadcast/rgb', rgb);
    }
}

/** Hex-Farbwert in RGB-Objekt umwandeln */
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    if (result) {
        return {
            r: Math.min(254, parseInt(result[1], 16)),
            g: Math.min(254, parseInt(result[2], 16)),
            b: Math.min(254, parseInt(result[3], 16))
        };
    }
    return null;
}

// ---------------------------------------------------------------------------
// Discovery
// ---------------------------------------------------------------------------

/** Bus-Scan starten */
async function scanBus() {
    const statusEl = document.getElementById('scan-status');
    const btnEl = document.getElementById('btn-scan');

    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.className = 'status-message info';
        statusEl.textContent = 'Scan läuft...';
    }
    if (btnEl) {
        btnEl.disabled = true;
    }

    const result = await apiPost('/api/v1/scan');

    if (result.status === 'scan_started') {
        // Polling auf Ergebnis (Scan dauert ~10-20 Sekunden)
        setTimeout(async () => {
            const devices = await apiRequest('/api/v1/devices');
            const count = Object.keys(devices).length;

            if (statusEl) {
                statusEl.className = 'status-message success';
                statusEl.textContent = `Scan abgeschlossen: ${count} Geräte gefunden`;
            }
            if (btnEl) {
                btnEl.disabled = false;
            }

            // Seite nach 2 Sekunden neu laden für aktualisierte Ansicht
            setTimeout(() => location.reload(), 2000);
        }, 15000);
    }
}

/** Commissioning starten */
async function commission(broadcast) {
    const statusEl = document.getElementById('commission-status');

    if (statusEl) {
        statusEl.style.display = 'block';
        statusEl.className = 'status-message info';
        statusEl.textContent = 'Adresszuweisung läuft...';
    }

    const result = await apiPost('/api/v1/commission', { broadcast });

    if (result.status === 'commissioning_started') {
        // Commissioning dauert länger
        setTimeout(async () => {
            const devices = await apiRequest('/api/v1/devices');
            const count = Object.keys(devices).length;

            if (statusEl) {
                statusEl.className = 'status-message success';
                statusEl.textContent = `Adresszuweisung abgeschlossen: ${count} Geräte`;
            }

            setTimeout(() => location.reload(), 2000);
        }, 30000);
    }
}

// ---------------------------------------------------------------------------
// Service-Info (Einstellungen)
// ---------------------------------------------------------------------------

/** Service-Status laden und anzeigen */
async function loadServiceInfo() {
    const result = await apiRequest('/api/v1/status');

    const firmwareEl = document.getElementById('info-firmware');
    const statusEl = document.getElementById('info-status');
    const devicesEl = document.getElementById('info-devices');

    if (firmwareEl) firmwareEl.textContent = result.firmware || '–';
    if (statusEl) statusEl.textContent = result.connected ? 'Verbunden' : 'Nicht verbunden';
    if (devicesEl) devicesEl.textContent = result.devices || '0';
}

// ---------------------------------------------------------------------------
// UI-Hilfsfunktionen
// ---------------------------------------------------------------------------

/** Slider-Label aktualisieren */
function updateSliderLabel(slider, labelId) {
    const label = document.getElementById(labelId);
    if (label) {
        label.textContent = slider.value;
    }
}

/** Geräte-Anzeige (Ein/Aus-Indikator) aktualisieren */
function updateDeviceIndicator(address, isOn) {
    const card = document.querySelector(`.device-card[data-address="${address}"]`);
    if (card) {
        const indicator = card.querySelector('.device-indicator');
        if (indicator) {
            indicator.classList.toggle('on', isOn);
            indicator.classList.toggle('off', !isOn);
        }
    }
}

/** Level-Bar in der Gerätekarte aktualisieren */
function updateLevelBar(address, level) {
    const card = document.querySelector(`.device-card[data-address="${address}"]`);
    if (card) {
        const fill = card.querySelector('.device-level-fill');
        if (fill) {
            fill.style.width = Math.round(level / 254 * 100) + '%';
        }
    }
}

// Tabellen-Status-Beschriftungen aus dem html-lang-Attribut ableiten,
// damit Englisch/Deutsch ohne extra Übergabe funktioniert.
const _DEV_STATE_LABELS = (document.documentElement.lang === 'en')
    ? { on: 'On', off: 'Off', absent: 'Unreachable' }
    : { on: 'Ein', off: 'Aus', absent: 'Nicht erreichbar' };

/** Zeile in der Geräte-Tabelle (devices.html) auf neuen Level aktualisieren:
 *  Klasse, Status-Badge und Slider-Wert-Anzeige synchron halten. */
function updateDeviceRow(address, level) {
    const row = document.querySelector(`tr.device-row[data-address="${address}"]`);
    if (!row) return;
    const newState = level > 0 ? 'on' : 'off';
    row.classList.remove('device-row-on', 'device-row-off', 'device-row-absent');
    row.classList.add('device-row-' + newState);
    const badge = row.querySelector('.device-state-badge');
    if (badge) {
        badge.classList.remove('device-state-on', 'device-state-off', 'device-state-absent');
        badge.classList.add('device-state-' + newState);
        badge.textContent = _DEV_STATE_LABELS[newState];
    }
    const valueEl = row.querySelector('.level-value');
    if (valueEl) valueEl.textContent = level;
    const slider = row.querySelector('input[type="range"].table-slider');
    if (slider) slider.value = level;
}

// ---------------------------------------------------------------------------
// Auto-Refresh (Dashboard-Status alle 10 Sekunden)
// ---------------------------------------------------------------------------
if (document.getElementById('queue-size')) {
    setInterval(async () => {
        const result = await apiRequest('/api/v1/status');
        const queueEl = document.getElementById('queue-size');
        if (queueEl && result.queue_size !== undefined) {
            queueEl.textContent = result.queue_size;
        }
    }, 10000);
}
