# Table of contents / Inhaltsverzeichnis
1. [DALI ServUI - english](#english)
2. [DALI ServUI - deutsch](#deutsch)
3. [Impressum](IMPRESSUM.md)
---

# DALI ServUI <a name="english"></a>

DALI ServUI is a web-based controller for [DALI](https://www.dali-alliance.org/)
lighting installations with multi-hardware support, REST API, server-sent
events and a multi-room dashboard.

Self-hosted, runs as a Docker container or natively as a systemd service
on a Raspberry Pi (or any Linux host).

---

## ⚠ Safety notice and disclaimer

Use of DALI ServUI is **at your own risk**. The author accepts no
liability for personal injury, property damage or financial loss
resulting from the use of this software.

DALI ServUI controls electrical lighting installations. Installation,
wiring and commissioning of the DALI bus system – in particular all work
on the mains-voltage side of the control gear – must only be carried out
by **qualified, trained personnel** (a licensed electrician). Applicable
national regulations (e. g. IEC 60364, BS 7671, NEC) must be observed.

---

## Features

- **Multi-hardware support**: Hasseb USB DALI Master (production-ready),
  MikroE DALI Click (GPIO + FTDI – coming soon), Dryrun test mode
- **Runtime driver switching** via the WebUI
- **DALI control**: broadcast, individual and group control, brightness
  (DAPC 0-254)
- **DT6 / DT8**: LED-gear queries, tunable white (Mirek/Kelvin), RGB
  colour control
- **Group management**: add/remove devices to/from groups via UI
- **Labels**: persistent device and group names
- **Multi-dashboard**: multiple dashboards (e. g. one per room), freely
  composed of devices and groups
- **Bus monitor**: real-time view of all TX/RX frames with readable DALI
  command descriptions
- **Bus sniffer**: passive listening on the DALI bus (Hasseb)
- **Discovery**: bus scan, commissioning (address assignment), address
  reset, factory reset – with live SSE output during commissioning
- **REST API v1**: full API with optional `X-API-Token` protection,
  CORS-enabled, ideal for Home Assistant
- **SSE events**: real-time stream (`/api/v1/events`) for level, group
  and scan updates
- **Healthz endpoint**: `GET /healthz` (auth-free) for container
  healthchecks
- **Bilingual**: German / English
- **Installation**: Docker or native systemd service (`install.sh`)

---

## Supported hardware

| Driver        | Hardware                                  | Connection                  | Library | Status        |
|---------------|-------------------------------------------|-----------------------------|---------|---------------|
| `hasseb`      | Hasseb USB DALI Master                    | USB-HID                     | hidapi  | production    |
| `mikroe_gpio` | MikroE DALI Click / DALI 2 Click          | Raspberry Pi GPIO           | gpiod   | coming soon   |
| `mikroe_ftdi` | MikroE DALI Click / DALI 2 Click          | Click USB Adapter (FT2232H) | pyftdi  | coming soon   |
| `dryrun`      | Test mode (no hardware)                   | –                           | –       | production    |

> The MikroE drivers are visible in the UI with a *Coming Soon* stamp.
> The Python dependencies `gpiod` and `pyftdi` are commented out in
> `requirements.txt` and must be installed manually before activating.

---

## Installation

### Native (Raspberry Pi / Debian / Ubuntu)

```bash
git clone https://git.zucker.network/zucker/public-apps/dali-servui.git
cd dali-servui/Code
sudo ./install.sh install
sudo systemctl start dali-servui
```

Web UI: `http://<host-ip>:5000`

### Docker

```bash
cd dali-servui/Docker
docker compose up -d
```

The container maps `/dev/hidraw0` for the Hasseb USB DALI Master by
default. Adjust the path in `docker-compose.yml` if needed.

---

## Configuration

| Variable             | Default     | Description                                                              |
|----------------------|-------------|--------------------------------------------------------------------------|
| `DALI_HOST`          | `0.0.0.0`   | Bind address                                                             |
| `DALI_PORT`          | `5000`      | TCP port                                                                 |
| `DALI_DRIVER`        | *(empty)*   | Initial driver (`hasseb`, `mikroe_gpio`, `mikroe_ftdi`, `dryrun`)        |
| `DALI_LANG`          | `de`        | UI language (`de` or `en`)                                               |
| `DALI_API_TOKEN`     | *(empty)*   | Optional API token. Empty = no auth                                      |
| `DALI_CORS_ORIGINS`  | *(empty)*   | Comma-separated origin list (`*` allowed but not default)                |
| `DALI_SECRET_KEY`    | *(empty)*   | Flask secret. Empty → generated in `data/secret_key` (0600)              |
| `DALI_DATA_DIR`      | `./data`    | Path for `driver_config.json`, `labels.json`, `devices.json`, `dashboards.json` |
| `DALI_LOG_LEVEL`     | `INFO`      | Log level                                                                |
| `DALI_LOG_FILE`      | *(empty)*   | Optional log file path                                                   |
| `DALI_DEBUG`         | `false`     | Flask debug mode                                                         |

---

## REST API (excerpt)

| Method  | Endpoint                                        | Description                       |
|---------|-------------------------------------------------|-----------------------------------|
| GET     | `/healthz`                                      | Container healthcheck (auth-free) |
| GET     | `/api/v1/status`                                | Service status                    |
| GET     | `/api/v1/events`                                | SSE stream (real-time events)     |
| GET     | `/api/v1/devices`                               | All devices                       |
| POST    | `/api/v1/devices/{addr}/level`                  | Set brightness                    |
| POST    | `/api/v1/devices/{addr}/on` / `/off`            | Turn on / off                     |
| GET     | `/api/v1/groups`                                | Groups with members and level     |
| POST    | `/api/v1/groups/{g}/on` / `/off` / `/level`     | Group control                     |
| GET/POST/PUT/DELETE | `/api/v1/dashboards[…]`             | Dashboard CRUD                    |
| POST    | `/api/v1/scan`                                  | Start bus scan                    |
| POST    | `/api/v1/commission`                            | Commissioning                     |

Full API documentation in the integrated help page (`/help`) and in
`Dokumentation/DALI_ServUI_Dokumentation_v1.0.0.md`.

---

## Security

- Optional `DALI_API_TOKEN` for the REST API (header `X-API-Token` or
  `?token=…` for SSE)
- Persistent `SECRET_KEY` in `data/secret_key` (mode 0600), generated
  automatically
- Strict CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`
- 5 MB cap on persisted JSON files; typed whitelist for driver config
- Cap on concurrent SSE listeners (50)
- systemd unit hardened (`NoNewPrivileges`, `ProtectSystem`,
  `ProtectHome`, `ReadWritePaths`, `PrivateTmp`)
- Container runs non-root with specific device mapping (`/dev/hidraw0`)
  instead of `privileged: true`

---

## AI Disclosure

DALI ServUI is developed with the assistance of
[Claude Code](https://claude.ai/code) (Claude by Anthropic), an AI
coding assistant used directly in the terminal.

**How AI is used in this project:**
- **Code generation**: modules, drivers, API routes, frontend logic and
  Docker configuration are written collaboratively with the AI based on
  requirements defined by the developer
- **Bug analysis & fixes**: the AI assists in identifying root causes
  and suggesting fixes, which the developer reviews and applies
- **Documentation**: README, changelogs, code comments and the
  integrated help page are drafted with AI assistance and reviewed by
  the developer
- **Architecture decisions**: all design decisions — feature scope,
  hardware support, security approach — are made by the developer; the
  AI implements them

**What the AI does not do:**
- Make autonomous commits or deploy code
- Define requirements or product direction
- Replace code review — all generated code is read and understood by
  the developer before use

The software is provided "as is" without warranty. Use at your own risk.

## Links

- [GitLab](https://git.zucker.network/zucker/public-apps/dali-servui)
- [Impressum / Legal Notice](IMPRESSUM.md)
- [Support](https://buymeacoffee.com/c42u)

---

# DALI ServUI <a name="deutsch"></a>

DALI ServUI ist ein web-basierter Controller für
[DALI](https://www.dali-alliance.org/)-Beleuchtungsanlagen mit
Multi-Hardware-Support, REST-API, Server-Sent-Events und Multi-Raum-
Dashboard.

Self-hosted, läuft als Docker-Container oder nativ als systemd-Service
auf einem Raspberry Pi (oder beliebigem Linux-Host).

---

## ⚠ Sicherheitshinweis und Haftungsausschluss

Die Nutzung von DALI ServUI erfolgt **auf eigene Gefahr**. Der Autor
übernimmt keine Haftung für Personen-, Sach- oder Vermögensschäden, die
durch den Einsatz dieser Software entstehen.

DALI ServUI steuert elektrische Beleuchtungsanlagen. Die Installation,
Verkabelung und Inbetriebnahme des DALI-Bus-Systems – insbesondere alle
Arbeiten an der Netzspannungsseite der Vorschaltgeräte – sind
ausschließlich durch **fachkundiges, ausgebildetes Personal**
(Elektrofachkraft) durchzuführen. Die jeweils geltenden nationalen
Vorschriften (z. B. DIN VDE 0100, ÖVE/ÖNORM E 8001, NIN) sind zu beachten.

---

## Funktionen

- **Multi-Hardware-Support**: Hasseb USB DALI Master (produktiv),
  MikroE DALI Click (GPIO + FTDI – Coming Soon), Dryrun-Testmodus
- **Treiber-Wechsel zur Laufzeit** über die WebUI
- **DALI-Steuerung**: Broadcast, Einzel- und Gruppensteuerung,
  Helligkeit (DAPC 0-254)
- **DT6 / DT8**: LED-Gear-Queries, Tunable White (Mirek/Kelvin),
  RGB-Farbsteuerung
- **Gruppenverwaltung**: Geräte zu Gruppen hinzufügen/entfernen per UI
- **Labels**: Persistente Namen für Geräte und Gruppen
- **Multi-Dashboard**: Mehrere Dashboards (z. B. pro Raum), frei aus
  Geräten und Gruppen zusammenstellbar
- **Bus-Monitor**: Echtzeit-Ansicht aller TX/RX-Frames mit lesbaren
  DALI-Befehlsbeschreibungen
- **Bus-Sniffer**: Passives Lauschen auf dem DALI-Bus (Hasseb)
- **Discovery**: Bus-Scan, Commissioning (Adresszuweisung),
  Adress-Reset, Factory Reset – mit Live-SSE-Output während des
  Commissioning
- **REST-API v1**: Vollständige API mit optionalem
  `X-API-Token`-Schutz, CORS-fähig, ideal für Home Assistant
- **SSE-Events**: Echtzeit-Stream (`/api/v1/events`) für Level-,
  Gruppen- und Scan-Updates
- **Healthz-Endpoint**: `GET /healthz` (auth-frei) für
  Container-Healthchecks
- **Zweisprachig**: Deutsch / Englisch
- **Installation**: Docker oder nativ mit systemd (`install.sh`)

---

## Unterstützte Hardware

| Treiber       | Hardware                                  | Anschluss                   | Bibliothek | Status            |
|---------------|-------------------------------------------|-----------------------------|------------|-------------------|
| `hasseb`      | Hasseb USB DALI Master                    | USB-HID                     | hidapi     | produktiv         |
| `mikroe_gpio` | MikroE DALI Click / DALI 2 Click          | Raspberry Pi GPIO           | gpiod      | in Vorbereitung   |
| `mikroe_ftdi` | MikroE DALI Click / DALI 2 Click          | Click USB Adapter (FT2232H) | pyftdi     | in Vorbereitung   |
| `dryrun`      | Testmodus (ohne Hardware)                 | –                           | –          | produktiv         |

> Die MikroE-Treiber sind im UI sichtbar mit *Coming-Soon*-Stempel. Die
> Python-Abhängigkeiten `gpiod` und `pyftdi` sind in `requirements.txt`
> auskommentiert und müssen vor dem Aktivieren manuell installiert
> werden.

---

## Installation

### Nativ (Raspberry Pi / Debian / Ubuntu)

```bash
git clone https://git.zucker.network/zucker/public-apps/dali-servui.git
cd dali-servui/Code
sudo ./install.sh install
sudo systemctl start dali-servui
```

Web-UI: `http://<host-ip>:5000`

### Docker

```bash
cd dali-servui/Docker
docker compose up -d
```

Der Container mappt standardmäßig `/dev/hidraw0` für den Hasseb USB
DALI Master. Pfad ggf. in `docker-compose.yml` anpassen.

---

## Konfiguration

| Variable             | Default     | Beschreibung                                                              |
|----------------------|-------------|---------------------------------------------------------------------------|
| `DALI_HOST`          | `0.0.0.0`   | Bind-Adresse                                                              |
| `DALI_PORT`          | `5000`      | TCP-Port                                                                  |
| `DALI_DRIVER`        | *(leer)*    | Initialer Treiber (`hasseb`, `mikroe_gpio`, `mikroe_ftdi`, `dryrun`)      |
| `DALI_LANG`          | `de`        | UI-Sprache (`de` oder `en`)                                               |
| `DALI_API_TOKEN`     | *(leer)*    | Optionaler API-Token. Leer = kein Auth                                    |
| `DALI_CORS_ORIGINS`  | *(leer)*    | Komma-getrennte Origin-Liste (`*` möglich, aber nicht Default)            |
| `DALI_SECRET_KEY`    | *(leer)*    | Flask-Secret. Leer → wird in `data/secret_key` (0600) generiert           |
| `DALI_DATA_DIR`      | `./data`    | Pfad für `driver_config.json`, `labels.json`, `devices.json`, `dashboards.json` |
| `DALI_LOG_LEVEL`     | `INFO`      | Log-Level                                                                 |
| `DALI_LOG_FILE`      | *(leer)*    | Optionaler Datei-Pfad für Logs                                            |
| `DALI_DEBUG`         | `false`     | Flask-Debug-Modus                                                         |

---

## REST-API (Auswahl)

| Methode | Endpunkt                                        | Beschreibung                                  |
|---------|-------------------------------------------------|-----------------------------------------------|
| GET     | `/healthz`                                      | Container-Healthcheck (auth-frei)             |
| GET     | `/api/v1/status`                                | Service-Status                                |
| GET     | `/api/v1/events`                                | SSE-Stream (Echtzeit-Events)                  |
| GET     | `/api/v1/devices`                               | Alle Geräte                                   |
| POST    | `/api/v1/devices/{addr}/level`                  | Helligkeit setzen                             |
| POST    | `/api/v1/devices/{addr}/on` / `/off`            | Ein-/Ausschalten                              |
| GET     | `/api/v1/groups`                                | Gruppen mit Mitgliedern und Level             |
| POST    | `/api/v1/groups/{g}/on` / `/off` / `/level`     | Gruppen-Steuerung                             |
| GET/POST/PUT/DELETE | `/api/v1/dashboards[…]`             | Dashboard-CRUD                                |
| POST    | `/api/v1/scan`                                  | Bus-Scan starten                              |
| POST    | `/api/v1/commission`                            | Commissioning                                 |

Vollständige API-Dokumentation in der integrierten Hilfe-Seite (`/help`)
und in `Dokumentation/DALI_ServUI_Dokumentation_v1.0.0.md`.

---

## Sicherheit

- Optionaler `DALI_API_TOKEN` für die REST-API (Header `X-API-Token`
  oder `?token=…` für SSE)
- Persistenter `SECRET_KEY` in `data/secret_key` (Modus 0600),
  automatisch generiert
- Strikte CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`
- 5-MB-Cap auf persistierte JSON-Dateien; typisierte Whitelist für
  Treiber-Config
- Cap auf gleichzeitige SSE-Listener (50)
- systemd-Unit gehärtet (`NoNewPrivileges`, `ProtectSystem`,
  `ProtectHome`, `ReadWritePaths`, `PrivateTmp`)
- Container läuft non-root mit spezifischem Device-Mapping
  (`/dev/hidraw0`) statt `privileged: true`

---

## KI-Transparenz

DALI ServUI wird unter Einsatz von [Claude Code](https://claude.ai/code)
(Claude von Anthropic), einem KI-Coding-Assistenten direkt im Terminal,
entwickelt.

**Wie KI in diesem Projekt eingesetzt wird:**
- **Code-Generierung**: Module, Treiber, API-Routen, Frontend-Logik und
  Docker-Konfiguration werden kollaborativ mit der KI auf Basis vom
  Entwickler definierter Anforderungen erstellt
- **Fehleranalyse & Behebung**: Die KI hilft bei der Ursachenanalyse
  und schlägt Lösungen vor, die der Entwickler prüft und umsetzt
- **Dokumentation**: README, Changelogs, Code-Kommentare und die
  integrierte Hilfe-Seite werden mit KI-Unterstützung verfasst und vom
  Entwickler geprüft
- **Architekturentscheidungen**: Alle Designentscheidungen —
  Feature-Umfang, Hardware-Support, Sicherheitsansatz — trifft der
  Entwickler; die KI setzt sie um

**Was die KI nicht tut:**
- Eigenständig committen oder Code deployen
- Anforderungen oder Produktrichtung bestimmen
- Code-Review ersetzen — jeder generierte Code wird vom Entwickler
  gelesen und verstanden, bevor er eingesetzt wird

Die Software wird "wie besehen" ohne jegliche Gewährleistung
bereitgestellt. Nutzung auf eigene Gefahr.

## Links

- [GitLab](https://git.zucker.network/zucker/public-apps/dali-servui)
- [Impressum](IMPRESSUM.md)
- [Unterstützung](https://buymeacoffee.com/c42u)
