# Changelog – DALI ServUI

Alle relevanten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.
Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)
und folgt [Semantic Versioning](https://semver.org/lang/de/).

## [1.0.0] – 2026-05-07

Erstes öffentliches Release. Funktional auf Stand von 0.9.0; Fokus dieser
Version: UI-Bugfixes, Aufräumen der Dokumentation und Versions-Konsistenz.

### Behoben
- **Geräte-Status-Spalte** zeigte unabhängig vom Schaltzustand immer einen
  grünen Punkt („present" wurde fälschlich als „eingeschaltet" gedeutet).
  Die Spalte zeigt jetzt drei Zustände als Pill-Badge analog zu den
  Gruppen-Mitgliedern: **Ein** (grün), **Aus** (grau),
  **Nicht erreichbar** (orange).
- **Geräte-Tabelle** bekommt zusätzlich einen dezenten Zeilen-Indikator
  (linker Farbbalken + leichter Hintergrund), damit der Ein/Aus-Zustand
  auf einen Blick erkennbar ist – Stilistik wie bei den
  Gruppen-Karten (`group-on/off/warning`).
- **Live-Update der Geräte-Tabelle**: `deviceOn` / `deviceOff` /
  `deviceLevel` aktualisieren das Status-Badge, die Zeilenklasse und den
  Slider-Wert ohne Reload (neue JS-Funktion `updateDeviceRow`).

### Geändert
- **Navbar-Eintrag „Kaffee?"** → **„Kaffee"** (Fragezeichen entfernt;
  EN: „Coffee?" → „Coffee").
- **Versions-Konsistenz**: Header-Drift in 21 Dateien (Python, HTML,
  CSS, JS, Bash, Dockerfile) behoben – alle führen jetzt Version 1.0.0
  und Deploy-Datum 2026-05-07.
- **Dokumentation aufgeräumt**: Alte Doku- und Reviewbericht-Stände
  (v0.2.0, v0.8.0, v0.9.0) aus `Dokumentation/` und `Reviewbericht/`
  nach `Versionssicherung/v<X.Y.Z>/` verschoben. In den jeweiligen
  Hauptordnern liegt nur noch die aktuelle Version.
- **README** komplett überarbeitet: Feature-Liste auf Stand 1.0.0,
  Tabelle der unterstützten Hardware mit Status-Spalte, vollständige
  Tabelle der ENV-Variablen, aktualisierte API-Übersicht, Hinweis auf
  buy-me-a-coffee.

### Doku
- Dokumentation v1.0.0 (MD + PDF)
- Reviewbericht v1.0.0 (MD + PDF)

## [0.9.0] – 2026-05-05

### Sicherheit
- **HTTP-Sicherheitsheader**: `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`
  und Content-Security-Policy (`default-src 'self'` plus `'unsafe-inline'`
  fuer Inline-Handler) auf allen Antworten
- **SSE-Listener-Cap** `MAX_SSE_LISTENERS = 50`; `subscribe_events`
  wirft `RuntimeError` bei Erreichen, `/api/v1/events` antwortet `503`
- **JSON-Loader-Haertung**: neuer `_safe_json_load()`-Helper mit
  Groessen-Cap (`MAX_JSON_BYTES = 5 MB`); auf `load_driver_config`,
  `load_labels`, `load_devices`, `load_dashboards` umgestellt
- **Typisierte Whitelist** in `load_driver_config` (`_DRIVER_CONFIG_FIELDS`):
  Werte mit falschem Typ werden verworfen, Default bleibt
- **Frontend-Auth via Meta-Tag**: Token aus `<meta name="x-api-token">`
  → JS sendet `X-API-Token`-Header; UI funktioniert auch bei gesetztem
  `DALI_API_TOKEN`
- **EventSource-Auth**: `api_auth_required` akzeptiert Token jetzt auch
  als `?token=...`-Query-Parameter (EventSource kann keine Custom-Header
  senden)

### Hinzugefuegt
- **Buy-me-a-coffee-Link** in der Navbar rechts neben „Hilfe"
  (`https://buymeacoffee.com/c42u`, oeffnet in neuem Tab,
  `rel="noopener noreferrer"`, `icon-coffee` aus Lucide ergaenzt)

### Doku
- Reviewbericht v0.9.0 (~6 Seiten PDF) mit Befunden und Fixes
- Dokumentation v0.9.0 (~23 Seiten PDF) – aktualisierte Sicherheitskapitel,
  Frontend-Auth-Abschnitt, Ressourcen-Caps-Tabelle, Coffee-Link
- CHANGELOG-Eintrag

### Geaendert
- Version auf 0.9.0 erhoeht

## [0.8.0] – 2026-05-05

### Hinzugefügt
- **MikroE Coming-Soon-Stempel** im Settings-Dialog
  - Treiber-Karten für `mikroe_gpio` und `mikroe_ftdi` erhalten ein schräg
    rotiertes „Coming Soon"-Overlay
  - Activate-Button durch *„In Vorbereitung" / „In preparation"* (disabled) ersetzt
  - Kennzeichnet die noch ausstehende Hardware-Validierung der MikroE-Boards
- **Healthz-Endpoint** `GET /healthz` (auth-frei) für Container-Healthchecks
- **CORS-Origins via ENV** `DALI_CORS_ORIGINS` (Komma-getrennte Liste,
  Default: leer = kein CORS-Header). `*` weiterhin möglich, aber nicht Default.
- **SECRET_KEY-Auto-Generierung** in `data/secret_key` (Mode 0600), wenn
  `DALI_SECRET_KEY` nicht oder mit dem Bootstrap-Default gesetzt ist
- **Dashboard-Item-Validierung**: Nur erlaubte Typen, Adressen 0..63,
  Gruppen-IDs 0..15
- **Label-Längen-Cap** (100 Zeichen) für Geräte- und Gruppennamen
- **Dedizierter Lock** für Commissioning-Log mit Helper-Funktionen
  (`_log_append`, `_log_clear`, `_log_snapshot`)
- **LICENSE**-Datei im Repo-Root (GPL-3.0-Volltext)
- **Dokumentation v0.8.0** komplett neu (~21 Seiten PDF), inkl. SSE,
  Multi-Dashboard, Commissioning, Bus-Sniffer, Sicherheit, MikroE-Status
- **Reviewbericht v0.8.0** mit Befunden und Fixes

### Behoben
- **Compose-Bug**: Doppelter `volumes:`-Block in `Docker/docker-compose.yml`
  (USB-Mapping wurde überschrieben). Volumes zusammengelegt, USB als
  spezifisches `devices: ["/dev/hidraw0:/dev/hidraw0"]` (statt `privileged: true`).
- **Healthcheck-Bug**: `HEALTHCHECK` rief `/api/v1/status` ohne Token →
  Container `unhealthy` bei gesetztem `DALI_API_TOKEN`. Auf `/healthz` umgestellt.
- **`signal.signal`** wird in `create_app()` registriert, damit auch der
  Gunicorn-Worker (nicht nur `__main__`) sauber herunterfährt.
- **`api_sniff` Duration**: `min(...)` ohne Floor erlaubte negative Werte;
  jetzt `max(0.5, min(raw, 60))` mit `try/except` für Type-Errors.

### Geändert
- Version auf 0.8.0 erhöht
- Dockerfile- und Compose-Header-Kommentare entdrifted

## [0.7.0] – 2026-04-04

### Hinzugefügt
- **Multi-Dashboard**: Mehrere Dashboards erstellbar (z.B. pro Raum)
  - Jedes Dashboard zeigt wahlweise alle Geräte, alle Gruppen, einzelne
    Geräte oder einzelne Gruppen – frei konfigurierbar
  - Statuskarten und Broadcast-Steuerung pro Dashboard ein-/ausschaltbar
  - Gruppen werden jetzt auch auf dem Dashboard angezeigt (group-cards)
  - Dashboard-Editor als Modal (Erstellen, Bearbeiten, Löschen)
  - Navbar-Dropdown zum schnellen Wechsel zwischen Dashboards
  - "default"-Dashboard ist geschützt und kann nicht gelöscht werden
  - Dashboard-Konfiguration persistent in dashboards.json gespeichert
- REST-API für Dashboards:
  - GET /api/v1/dashboards – Alle Dashboards
  - GET /api/v1/dashboards/{id} – Einzelnes Dashboard
  - POST /api/v1/dashboards – Dashboard erstellen
  - PUT /api/v1/dashboards/{id} – Dashboard aktualisieren
  - DELETE /api/v1/dashboards/{id} – Dashboard löschen
- Wiederverwendbares _group_card.html Partial (Dashboard + Gruppen-Seite)

### Geändert
- Route `/` redirected jetzt auf aktives Dashboard (`/dashboard/<id>`)
- groups.html nutzt _group_card.html Partial
- Version auf 0.7.0 erhöht

## [0.6.0] – 2026-04-04

### Hinzugefügt
- **Gruppen-API**: GET /api/v1/groups – Alle Gruppen mit Name, Mitgliedern und Level
  - Ideal für Home Assistant Integration (kein manuelles Zusammenbauen aus /devices + /labels)
- **CORS-Header** für alle /api/ Endpunkte
  - Erlaubt Zugriff von externen Clients (Home Assistant, Custom Components, Dashboards)
  - Access-Control-Allow-Origin: *, Headers: Content-Type + X-API-Token
- **SSE-Event-Stream**: GET /api/v1/events – Server-Sent Events bei Zustandsänderungen
  - Event-Typen: level, on, off, group_on, group_off, group_level,
    scan_complete, colour_temp, rgb
  - Keepalive alle 30 Sekunden (verhindert Timeout)
  - Mehrere gleichzeitige Clients möglich (Thread-sicherer Event-Bus)

### Geändert
- Version auf 0.6.0 erhöht

## [0.5.1] – 2026-04-04

### Hinzugefügt
- Globaler Aktivitäts-Indikator (Spinner) in der Navbar bei laufenden API-Aktionen
  - Rotierendes Activity-Icon neben dem Verbindungsstatus
  - Automatisch bei allen API-Requests und Commissioning-Stream aktiv
  - Referenzzähler für parallele Requests (Spinner bleibt bis alle fertig)
- Automatischer Bus-Scan nach Commissioning – Geräte sind sofort in der UI sichtbar
- Commissioning-Lock: Verhindert gleichzeitige Ausführung (HTTP 409 bei Doppelstart)
- Commissioning-Output-Buffer: Gepufferte Ausgabe im Backend
  - Neuer Endpunkt GET /api/v1/drivers/commission-status (running + log)
- Commissioning: Warnhinweis beim Start und Seitenverlassen-Schutz
  - Gelbe Warnbox auf der Erkennung-Seite während Commissioning sichtbar
  - Browser-Dialog (beforeunload) und Navbar-Klick-Confirm bei laufender Aktion
  - Confirm-Dialog enthält Hinweis, dass die Seite nicht verlassen werden darf

### Behoben
- Commissioning-Stream: Fehlender `import time` in main.py brach den SSE-Stream ab
  - Erster Klick zeigte nur "Treiber gestoppt / Verbindung unterbrochen"
  - Zweiter Klick war nötig um Commissioning tatsächlich zu starten
- Commissioning: USB-Settle-Time von 0.5s auf 1.5s erhöht (zuverlässigere Freigabe)
- Commissioning: Doppeltes [DONE]-Event im SSE-Stream entfernt (try/finally → linearer Ablauf)
- Commissioning: Nach Abschluss wird Treiber neu gestartet UND Bus-Scan ausgeführt
- Commissioning: Navigation weg und zurück + erneuter Klick crashte den Hasseb (Lock behebt das)

### Geändert
- Alle ASCII-Umschreibungen (ae/oe/ue) in Kommentaren, Docstrings und Strings
  durch echte Umlaute ersetzt (~180 Stellen in 18 Dateien)
- Version auf 0.5.1 erhöht

## [0.5.0] – 2026-04-04

### Hinzugefügt
- Commissioning mit Live-Output in der UI (SSE-Stream)
  - "Neuadressierung starten" Button auf der Erkennung-Seite
  - Echtzeit-Terminal-Ausgabe (Adressen löschen, Commissioning, Bus-Scan)
  - Treiber wird automatisch gestoppt und nach Abschluss neu gestartet
- Commissioning via python-dali für Hasseb (stabil mit 21 EVGs getestet)
  - Nutzt python-dali v0.11 run_sequence(Commissioning()) API
  - Factory Reset + Adress-Löschung + Commissioning + Bus-Scan
- Adress-Reset: "Alle Adressen löschen" Button (DTR=0xFF + Initialise + SetShortAddress)
- Factory Reset: "Factory Reset" Button (Broadcast RESET 0x20)
- Bus-Sniffer: Passives Lauschen auf DALI-Frames (Hasseb Sniffer-Modus)
  - "Bus lauschen" Button auf der Protokoll-Seite mit einstellbarer Dauer
- CLI-Skript dali_commission.py für standalone Commissioning
  - Optionen: --reset-only, --scan-only, --no-reset
- Treiber Stop/Start API: POST /api/v1/drivers/stop, /api/v1/drivers/start
- REST-API: /api/v1/sniff, /api/v1/reset-addresses, /api/v1/factory-reset

### Behoben
- Hasseb: Buffer-Flush vor expect_reply-Frames (verhindert USB-Crash)
- Hasseb: Write-Retry mit automatischem Reconnect bei HID-Sendefehler
- Hasseb: Längere Timeouts und Settling Time bei send_twice Frames
- Commissioning: Withdraw als Spezialbefehl (0xAB, 0x00)
- Commissioning: Iterative Binary Search statt rekursiv
- Bus-Scan: query_device_present mit Retry bei SEND_ERROR

### Geändert
- Commissioning bei Hasseb läuft über python-dali Subprocess (statt eigener Impl.)
- Version auf 0.5.0 erhöht

## [0.4.2] – 2026-04-04

### Hinzugefügt
- Geräte-Persistierung: Scan-Ergebnisse werden in devices.json gespeichert
  und beim Service-Start automatisch geladen (kein Datenverlust bei Neustart/Update)
- Lucide Icons (offline SVG Sprite, 20 Icons, ISC-Lizenz)
  - Navigation mit Icons (Dashboard, Geräte, Gruppen, Erkennung, Einstellungen, Protokoll, Hilfe)
  - Status-Badge mit Wifi/Wifi-Off Icon
  - Lizenz-Attribution im Footer

### Behoben
- Commissioning: Withdraw als Spezialbefehl (0xAB, 0x00) statt Gerätebefehl
- Commissioning: Verify nutzt korrekte Adresse 0xB9 (statt 0xB5 SearchAddrL)
- Commissioning: Randomise-Wartezeit auf 200ms erhöht (EVGs brauchen Zeit für Random-Adresse)

### Geändert
- Version auf 0.4.2 erhöht

## [0.4.0] – 2026-04-03

### Hinzugefügt
- Bus-Protokoll: Echtzeit-Monitor für DALI-Debugging (/buslog)
  - Ringbuffer (500 Einträge) mit allen TX/RX Frames
  - Lesbare Frame-Beschreibungen (DAPC, DTR, DT6/DT8, Commissioning)
  - Auto-Refresh (1s Polling), Pause, Clear
  - Raw DALI-Befehl direkt aus der Monitor-Seite senden
- Gruppenzuweisung: Geräte per UI zu Gruppen hinzufügen/entfernen
  - DALI AddToGroup (0x60-0x6F) und RemoveFromGroup (0x70-0x7F)
  - Modal-Dialog mit Gruppenauswahl (0-15)
  - Gruppen-Badges mit × zum Entfernen
- Labels: Persistierte Namen für Geräte und Gruppen (labels.json)
  - Inline-Editierbare Namensfelder auf Geräte- und Gruppen-Seite
  - Namen werden im Dashboard, Geräte- und Gruppen-Seite angezeigt
- REST-API: /api/v1/buslog, /api/v1/buslog/toggle
- REST-API: /api/v1/labels/device/{addr}, /api/v1/labels/group/{g}
- REST-API: POST/DELETE /api/v1/devices/{addr}/groups
- Nav-Link "Protokoll" in der Navigation

### Geändert
- FTDI-Treiber komplett auf Buffered Async Bitbang umgestellt
  - Gesamte Manchester-Wellenform als Byte-Buffer vorberechnet
  - FTDI-Chip taktet Pins selbständig mit 9600 Hz (baudrate=600, ×16)
  - RX: Blockweises Lesen und Manchester-Decodierung
- FTDI: TX-Default auf invertiert (DALI Click v1: OUT=1=idle)
- FTDI: RX-Invertierung für DALI Click v1 (Pin HIGH = idle)
- udev-Regeln in einer Datei zusammengefasst (99-dali-servui.rules)
  - Hasseb: hidraw + USB-Regel (hidapi Fallback)
  - FTDI: USB-Regel
  - Alte Einzelregeln werden beim Install aufgeräumt
- install.sh: dali-User in plugdev+dialout für USB-Zugriff
- Bus-Protokoll: Sticky Header mit solidem Hintergrund (kein Durchscheinen)
- Version auf 0.4.0 erhöht

## [0.3.0] – 2026-03-23

### Hinzugefügt
- DT6-Support: LED Gear spezifische Queries (Operating Mode, Thermal Status)
- DT8 Tunable White: Farbtemperatur-Steuerung in Mirek/Kelvin (2700K–6500K)
- DT8 RGB: Farbsteuerung über RGBWAF-Kanäle
- Feature-Toggles in Einstellungen: DT6, DT8 Tc, DT8 RGB einzeln aktivierbar
- Farbtemperatur-Slider (warm↔kalt Gradient) im Dashboard und Geräte-Karten
- RGB Colour-Picker im Dashboard und Geräte-Karten
- DT8-Erkennung beim Bus-Scan (Colour Type Features, supports_tc, supports_rgb)
- REST-API: /api/v1/features, /api/v1/devices/{addr}/colour-temp, /api/v1/devices/{addr}/rgb
- REST-API: /api/v1/broadcast/colour-temp, /api/v1/broadcast/rgb
- Hilfe-Seite um DT6/DT8-Abschnitt erweitert

### Geändert
- DaliDevice um DT8-Felder erweitert (colour_temp_mirek, rgb_r/g/b, supports_tc/rgb)
- DaliDriverConfig um Feature-Flags erweitert (feature_dt6, feature_dt8_tc, feature_dt8_rgb)
- Bus-Scan erkennt DT8-Geräte und liest Colour Type Features aus
- Version auf 0.3.0 erhöht

## [0.2.0] – 2026-03-22

### Hinzugefügt
- Integrierte Hilfe-Seite (DE/EN) mit vollständiger Anleitung zu Hardware, Installation, API, Fehlerbehebung
- Dokumentation nach Standardregel (Markdown + PDF, 14 Seiten)
- Plugin-Treiber-Architektur mit 4 austauschbaren Treibern:
  - Hasseb USB DALI Master (USB-HID)
  - MikroE DALI Click / DALI 2 Click via GPIO (Raspberry Pi + Pi Click Shield)
  - MikroE DALI Click / DALI 2 Click via Click USB Adapter (FTDI FT2232H)
  - Dryrun-Testmodus (ohne Hardware)
- Treiber-Auswahl und -Konfiguration über WebUI (Einstellungen-Seite)
- Treiber-Wechsel zur Laufzeit mit Konfigurations-Persistierung (JSON)
- REST-API Endpunkte: /api/v1/drivers, /api/v1/drivers/switch, /api/v1/drivers/config
- Unterstützung für DALI Click TX-Invertierung (DALI Click vs. DALI 2 Click)
- GPIO-Pin-Konfiguration und FTDI-Device-URL über WebUI einstellbar

### Geändert
- dali_service.py refaktoriert: Treiber-Logik in separate Module ausgelagert
- config.py: DALI_DRYRUN ersetzt durch DALI_DRIVER (hasseb|mikroe_gpio|mikroe_ftdi|dryrun)
- Version auf 0.2.0 erhöht

## [0.1.0] – 2026-03-21

### Hinzugefügt
- Initiale Projektstruktur nach Standardregel
- Projektbeschreibung und Projektidee
- GitLab-Repository unter zucker/public-apps/dali-servui
