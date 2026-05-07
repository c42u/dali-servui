# DALI ServUI

Web-basierte DALI-Lichtsteuerung mit Multi-Hardware-Support, REST-API,
Server-Sent-Events und Multi-Dashboard. Läuft als Container oder als
nativer systemd-Service auf einem Raspberry Pi (oder beliebigem Linux).

**Autor:** c42u | **Co-Autor:** ClaudeCode | **Lizenz:** GPLv3 | **Version:** 1.0.0

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

## Features

- **Multi-Hardware-Support:** Hasseb USB DALI Master (produktiv getestet),
  MikroE DALI Click (GPIO + FTDI – in Vorbereitung), Dryrun-Testmodus
- **Treiber-Wechsel zur Laufzeit** über die WebUI
- **DALI-Steuerung:** Broadcast, Einzel- und Gruppensteuerung,
  Helligkeit (DAPC 0-254)
- **DT6 / DT8:** LED-Gear-Queries, Tunable White (Mirek/Kelvin),
  RGB-Farbsteuerung
- **Gruppenverwaltung:** Geräte zu Gruppen hinzufügen/entfernen per UI
- **Labels:** Persistente Namen für Geräte und Gruppen
- **Multi-Dashboard:** Mehrere Dashboards (z. B. pro Raum), frei aus
  Geräten und Gruppen zusammenstellbar
- **Bus-Protokoll:** Echtzeit-Monitor aller TX/RX-Frames inkl. lesbarer
  DALI-Befehlsbeschreibungen
- **Bus-Sniffer:** Passives Lauschen auf DALI-Frames (Hasseb)
- **Discovery:** Bus-Scan, Commissioning (Adresszuweisung), Adress-Reset,
  Factory Reset – inklusive Live-Output (SSE) während des Commissioning
- **Aktivitäts-Indikator:** Globaler Spinner während laufender API-Aktionen
- **REST-API v1:** Vollständige API mit optionalem `X-API-Token`-Schutz,
  CORS-fähig, ideal für Home Assistant
- **SSE-Events:** Echtzeit-Stream (`/api/v1/events`) für Level-, Gruppen-
  und Scan-Updates; auch mit Token (`?token=…`) konsumierbar
- **Sicherheits-Header:** CSP, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` auf
  allen Antworten
- **SSE-Listener-Cap** und **5-MB-JSON-Cap** als Schutz gegen
  Ressourcenmissbrauch
- **Frontend-Auth via Meta-Tag:** Token wird (falls gesetzt) ins HTML
  injiziert, damit die UI auch bei aktiviertem `DALI_API_TOKEN` direkt
  funktioniert
- **Healthz-Endpoint:** `GET /healthz` (auth-frei) für Container-Healthchecks
- **Persistenter SECRET_KEY:** wird beim ersten Start in
  `data/secret_key` (0600) erzeugt
- **Zweisprachig:** Deutsch / Englisch
- **Installation:** Docker oder nativ mit systemd (`install.sh`)

## Unterstützte Hardware

| Treiber       | Hardware                                  | Anschluss               | Bibliothek | Status            |
|---------------|-------------------------------------------|-------------------------|-----------:|-------------------|
| `hasseb`      | Hasseb USB DALI Master                    | USB-HID                 | hidapi     | produktiv         |
| `mikroe_gpio` | MikroE DALI Click / DALI 2 Click          | Raspberry Pi GPIO       | gpiod      | in Vorbereitung   |
| `mikroe_ftdi` | MikroE DALI Click / DALI 2 Click          | Click USB Adapter (FT2232H) | pyftdi | in Vorbereitung   |
| `dryrun`      | Testmodus (ohne Hardware)                 | –                       | –          | produktiv         |

> **Hinweis:** Die MikroE-Treiber sind im UI sichtbar mit *Coming-Soon*-
> Stempel. Die Python-Abhängigkeiten `gpiod` und `pyftdi` sind in
> `requirements.txt` auskommentiert und müssen vor dem Aktivieren manuell
> installiert werden.

## Schnellstart

### Native Installation (Raspberry Pi / Debian / Ubuntu)

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

## Konfiguration (Umgebungsvariablen)

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

## Projektstruktur

```
dali-servui/
├── Changelog/CHANGELOG.md
├── Code/
│   ├── app/
│   │   ├── drivers/             Treiber (hasseb, mikroe_gpio, mikroe_ftdi, dryrun)
│   │   ├── static/              CSS, JavaScript, Lucide-Icons
│   │   ├── templates/           Jinja2-Templates (Dashboard, Geräte, Gruppen, …)
│   │   ├── config.py            Konfiguration (ENV-basiert)
│   │   ├── dali_service.py      DALI-Service (Queue, Befehle, Bus-Log)
│   │   ├── main.py              Flask-App + REST-API
│   │   └── translations.py      Übersetzungen (DE/EN)
│   ├── dali_commission.py       CLI-Skript für standalone Commissioning
│   ├── install.sh               Installations-Skript (systemd + udev)
│   ├── backup.sh / restore.sh   Backup-/Restore der Konfigurationsdateien
│   └── requirements.txt         Python-Abhängigkeiten
├── Docker/
│   ├── Dockerfile               Multi-Stage-Build mit USB-HID-Support
│   └── docker-compose.yml       Compose mit Healthcheck und USB-Passthrough
├── Dokumentation/               Aktuelle Doku (MD + PDF)
├── Reviewbericht/               Aktueller Reviewbericht
├── Versionssicherung/           Archivierte Doku/Reviewberichte älterer Releases
├── Projektbeschreibung/
├── Projektverlauf/
├── LICENSE                      GPL-3.0 Volltext
└── README.md
```

## REST-API (Auswahl)

| Methode | Endpunkt                                  | Beschreibung                                  |
|---------|-------------------------------------------|-----------------------------------------------|
| GET     | `/healthz`                                | Container-Healthcheck (auth-frei)             |
| GET     | `/api/v1/status`                          | Service-Status                                |
| GET     | `/api/v1/events`                          | SSE-Stream (Echtzeit-Events)                  |
| GET     | `/api/v1/devices`                         | Alle Geräte                                   |
| POST    | `/api/v1/devices/{addr}/level`            | Helligkeit setzen                             |
| POST    | `/api/v1/devices/{addr}/on` / `/off`      | Ein-/Ausschalten                              |
| GET     | `/api/v1/groups`                          | Gruppen mit Mitgliedern und Level             |
| POST    | `/api/v1/groups/{g}/on` / `/off` / `/level` | Gruppen-Steuerung                          |
| POST    | `/api/v1/devices/{addr}/groups`           | Zu Gruppe hinzufügen                          |
| DELETE  | `/api/v1/devices/{addr}/groups`           | Aus Gruppe entfernen                          |
| POST    | `/api/v1/labels/device/{addr}`            | Gerätename setzen                             |
| POST    | `/api/v1/labels/group/{g}`                | Gruppenname setzen                            |
| GET/POST/PUT/DELETE | `/api/v1/dashboards[…]`         | Dashboard-CRUD                                |
| GET     | `/api/v1/buslog`                          | Bus-Protokoll abrufen                         |
| POST    | `/api/v1/scan`                            | Bus-Scan starten                              |
| POST    | `/api/v1/commission`                      | Commissioning                                 |
| GET     | `/api/v1/drivers/commission-stream`       | Commissioning mit SSE-Live-Output             |
| POST    | `/api/v1/drivers/switch`                  | Treiber wechseln                              |

Vollständige API-Dokumentation in der integrierten Hilfe-Seite (`/help`)
und in `Dokumentation/DALI_ServUI_Dokumentation_v1.0.0.md`.

## Spenden

Wer das Projekt unterstützen möchte:
[buymeacoffee.com/c42u](https://buymeacoffee.com/c42u)

## Lizenz

GPLv3 – siehe [LICENSE](LICENSE)
