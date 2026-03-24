# GitTranslate Einrichtungsanleitung

GitTranslate funktioniert mit jedem externen Git-Anbieter (GitHub, GitLab, Gitea, etc.). Es kann mit Docker oder direkt mit Python betrieben werden.

---

## Voraussetzungen: Ollama

1. Ollama installieren: https://ollama.com/download
2. Ein Modell herunterladen:
   ```bash
   ollama pull translategemma:4b
   ```
3. Betrieb prüfen: `curl http://localhost:11434/`

---

## Option A — Mit Docker

### 1. Docker installieren

Docker Desktop installieren (enthält Docker Compose):
https://www.docker.com/products/docker-desktop/
- macOS / Windows: Installer herunterladen und ausführen
- Linux: Der [Engine-Installationsanleitung](https://docs.docker.com/engine/install/) folgen und das Compose-Plugin separat installieren

Verfügbarkeit prüfen:
```bash
docker --version
docker compose version
```

### 2. `.env` konfigurieren

```bash
cp .env.example .env
```

Vollständige HTTPS-URLs und persönliche Zugriffstoken für die Repos setzen:
```
SRC_GIT_URL=https://github.com/youruser/thesis-de
SRC_GIT_TOKEN=ghp_xxxxxxxxxxxx

TARGET_GIT_URL=https://github.com/youruser/thesis-en
TARGET_GIT_TOKEN=ghp_xxxxxxxxxxxx

LLM_MODEL=translategemma:4b
LLM_API_URL=http://host.docker.internal:11434
```

**GitHub**: Einstellungen → Entwicklereinstellungen → Personal access tokens → Fine-grained
Erforderliche Berechtigungen: `Contents` (Lesen für Quelle, Lesen+Schreiben für Ziel)

**GitLab**: Benutzereinstellungen → Zugriffstoken → `read_repository` + `write_repository`

### 3. Worker starten

```bash
docker compose up -d
```

### 4. Übersetzung auslösen

```bash
curl -X POST http://localhost:8000/sync
```

Der Worker vergleicht den aktuellen HEAD SHA mit dem zuletzt verarbeiteten SHA (gespeichert in einem Docker-Volume). Beim ersten Aufruf werden alle `.tex`-Dateien im Quell-Repo übersetzt. Folgeaufrufe verarbeiten nur geänderte Dateien.

---

## Option B — Ohne Docker

### 1. Voraussetzungen

- Python 3.10+
- Git
- Ollama (siehe oben)

### 2. `.env` konfigurieren

```bash
cp .env.example .env
```

Repos, Tokens und Modell setzen:
```
SRC_GIT_URL=https://github.com/youruser/thesis-de
SRC_GIT_TOKEN=ghp_xxxxxxxxxxxx

TARGET_GIT_URL=https://github.com/youruser/thesis-en
TARGET_GIT_TOKEN=ghp_xxxxxxxxxxxx

LLM_MODEL=translategemma:4b
LLM_API_URL=http://localhost:11434
STATE_DIR=./state
```

> **Wichtig:** `STATE_DIR=./state` setzen, damit der Sync-Status lokal gespeichert wird (der Standard `/app/state` gilt nur innerhalb von Docker).

### 3. Abhängigkeiten installieren und starten

```bash
cd worker
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 4. Übersetzung auslösen

In einem anderen Terminal:
```bash
curl -X POST http://localhost:8000/sync
```

---

## Sync automatisieren

**Option A — Cron-Job** (z. B. alle 5 Minuten):
```
*/5 * * * * curl -s -X POST http://localhost:8000/sync
```

**Option B — Integriertes Polling**: `POLL_INTERVAL` in `.env` setzen (Sekunden):
```
POLL_INTERVAL=300
```
Der Worker pollt automatisch beim Start, kein externer Scheduler erforderlich.

**Option C — Webhooks** (erfordert eine öffentliche URL / Tunnel):

Für lokale Entwicklung einen Tunnel verwenden (z. B. [ngrok](https://ngrok.com)):
```bash
ngrok http 8000
# → https://abc123.ngrok.io
```

**GitHub**: Repo → Einstellungen → Webhooks → Webhook hinzufügen
- **Payload URL**: `https://abc123.ngrok.io/webhook`
- **Content type**: `application/json`
- **Secret**: Einen Wert hier und in `.env` als `WEBHOOK_SECRET` setzen
- **Ereignisse**: Nur das Push-Ereignis

**GitLab**: Repo → Einstellungen → Webhooks
- **URL**: `https://abc123.ngrok.io/webhook`
- **Secret token**: gleich wie `WEBHOOK_SECRET`
- **Auslöser**: Push-Ereignisse

---

## Webhook-Geheimnisvalidierung

`WEBHOOK_SECRET` in `.env` setzen und denselben Wert in den Webhook-Einstellungen des Git-Anbieters verwenden.

GitTranslate akzeptiert alle gängigen Anbieterformate:
- **GitHub-Format**: `X-Hub-Signature-256: sha256=<hex>` (HMAC-SHA256)
- **Gitea-Format**: `X-Gitea-Signature: <hex>` (HMAC-SHA256)
- **GitLab-Format**: `X-Gitlab-Token: <Geheimnis>` (Klartextvergleich)

Ungültige Anfragen erhalten HTTP 401 zurück.

---

## Sprachpaar konfigurieren

Quell- und Zielsprache sind konfigurierbar:
```
SOURCE_LANG=German
TARGET_LANG=English
```

Diese auf ein beliebiges Sprachpaar ändern, das das LLM unterstützt.

---

## Health Check

```bash
curl http://localhost:8000/
```

Gibt eine JSON-Zusammenfassung der aktuellen Konfiguration zurück.

---

## Fehlerbehebung

### Worker startet nicht — "Field required"-Validierungsfehler
Das Docker-Image ist veraltet. Nach jeder Code- oder Konfigurationsänderung neu bauen:
```bash
docker compose up -d --build worker
```

### 403 „Write access to repository not granted" bei `/sync`
Das Token hat nicht die erforderlichen Berechtigungen. Für GitHub Fine-grained PATs:

- **Quell-Repo** (`thesis-de`): `Contents` → **Read**
- **Ziel-Repo** (`thesis-en`): `Contents` → **Read and Write**

Pfad: GitHub → Einstellungen → Entwicklereinstellungen → Personal access tokens → Fine-grained tokens → Token bearbeiten.

> Tipp: Wenn das Token in Logs sichtbar ist, sofort neu generieren.

### „Remote branch main not found" beim ersten `/sync`
Das Ziel-Repo ist leer und hat noch keinen `main`-Branch. Vor dem Start initialisieren:

**Option A — GitHub UI:** Repo öffnen und auf *Initialize this repository* klicken.

**Option B — Kommandozeile:**
```bash
git clone https://github.com/youruser/thesis-en.git
cd thesis-en
git commit --allow-empty -m "init"
git push origin main
```

Danach `/sync` erneut aufrufen.
