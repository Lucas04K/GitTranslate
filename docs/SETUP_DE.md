# GitTranslate Einrichtungsanleitung

GitTranslate unterstützt zwei Betriebsmodi:

| Modus | Git-Anbieter | Wann verwenden |
|-------|-------------|----------------|
| **A – Lokal** | Gitea (selbst gehostet, via Docker) | Lokale Entwicklung / air-gapped Setup |
| **B – Extern** | GitHub, GitLab, beliebige Gitea-Instanz | Produktion / bestehende Repos |

Beide Modi erfordern Ollama auf dem Host-Rechner.

---

## Voraussetzungen: Docker

1. Docker Desktop installieren (enthält Docker Compose):
   https://www.docker.com/products/docker-desktop/
   - macOS / Windows: Installer herunterladen und ausführen
   - Linux: Der [Engine-Installationsanleitung](https://docs.docker.com/engine/install/) folgen und das Compose-Plugin separat installieren
2. Verfügbarkeit prüfen:
   ```bash
   docker --version
   docker compose version
   ```

---

## Voraussetzungen: Ollama

1. Ollama installieren: https://ollama.com/download
2. Ein Modell herunterladen:
   ```bash
   ollama pull translategemma:4b
   ```
3. Betrieb prüfen: `curl http://localhost:11434/`

---

## Modus A — Lokales Gitea + Ollama

### 1. `.env` konfigurieren

Beispieldatei kopieren und Werte eintragen:
```bash
cp .env.example .env
```

Mindestens setzen:
```
SRC_GIT_URL=http://gitea:3000/admin/repo-de
TARGET_GIT_URL=http://gitea:3000/admin/repo-en
LLM_MODEL=translategemma:4b
```
`SRC_GIT_TOKEN` / `TARGET_GIT_TOKEN` vorerst leer lassen — diese werden nach dem Start von Gitea eingetragen.

### 2. Alle Dienste starten

```bash
docker compose --profile local-git up -d
```

### 3. Gitea-Erstkonfigurationsassistent

http://localhost:3000 öffnen (oder `GITEA_HTTP_PORT`, falls geändert).

- Das erste erstellte Konto wird zum Administratorkonto.
- Alle Datenbankstandards übernehmen (bereits über die Umgebung konfiguriert).

### 4. Repositories erstellen

In der Gitea-Weboberfläche:
- `repo-de` erstellen (Quelle, Deutsch)
- `repo-en` erstellen (Ziel, Englisch)

Oder via API:
```bash
curl -s -X POST http://localhost:3000/api/v1/user/repos \
  -u admin:admin123 -H "Content-Type: application/json" \
  -d '{"name":"repo-de","private":false}'
```

### 5. Zugriffstoken generieren

**Gitea UI → Benutzereinstellungen → Anwendungen → Token generieren**

Token in `.env` eintragen:
```
SRC_GIT_TOKEN=<token>
TARGET_GIT_TOKEN=<token>
```

### 6. Worker neu erstellen

```bash
docker compose --profile local-git up -d --build worker
```

### 7. Webhook konfigurieren

In Gitea: **repo-de → Einstellungen → Webhooks → Webhook hinzufügen → Gitea**

- **Ziel-URL**: `http://worker:8000/webhook`
  (`http://host.docker.internal:8000/webhook` verwenden, wenn der Worker außerhalb von Docker läuft)
- **Content type**: `application/json`
- **Geheimnis**: Optional einen Wert setzen und in `.env` als `WEBHOOK_SECRET` eintragen
- **Auslöser**: Push-Ereignisse

### 8. Testen

Eine `.tex`-Datei in `repo-de` pushen. Logs beobachten:
```bash
docker compose logs -f worker
```

---

## Modus B — Externes Git (GitHub / GitLab) + Ollama

### 1. `.env` konfigurieren

```bash
cp .env.example .env
```

Vollständige HTTPS-URLs und persönliche Zugriffstoken für die Repos setzen:
```
SRC_GIT_URL=https://github.com/youruser/repo-de
SRC_GIT_TOKEN=ghp_xxxxxxxxxxxx

TARGET_GIT_URL=https://github.com/youruser/repo-en
TARGET_GIT_TOKEN=ghp_xxxxxxxxxxxx

LLM_MODEL=translategemma:4b
```

**GitHub**: Einstellungen → Entwicklereinstellungen → Personal access tokens → Fine-grained
Erforderliche Berechtigungen: `Contents` (Lesen für Quelle, Lesen+Schreiben für Ziel)

**GitLab**: Benutzereinstellungen → Zugriffstoken → `read_repository` + `write_repository`

### 2. Nur den Worker starten

```bash
docker compose up worker -d
```

Gitea und Datenbank werden nicht gestartet (diese erfordern `--profile local-git`).

### 3. Übersetzung mit `/sync` auslösen

Kein Webhook oder öffentliche URL erforderlich. `POST /sync` verwenden, um neue Commits zu prüfen und zu übersetzen:

```bash
# Einmaliger manueller Sync
curl -X POST http://localhost:8000/sync
```

Der Worker vergleicht den aktuellen HEAD SHA mit dem zuletzt verarbeiteten SHA (gespeichert in einem Docker-Volume). Beim ersten Aufruf werden alle `.tex`-Dateien im Quell-Repo übersetzt. Folgeaufrufe verarbeiten nur geänderte Dateien.

### 4. Sync automatisieren

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

GitTranslate akzeptiert alle drei Anbieterformate:
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

- **Quell-Repo** (`repo-de`): `Contents` → **Read**
- **Ziel-Repo** (`repo-en`): `Contents` → **Read and Write**

Pfad: GitHub → Einstellungen → Entwicklereinstellungen → Personal access tokens → Fine-grained tokens → Token bearbeiten.

> Tipp: Wenn das Token in Logs sichtbar ist, sofort neu generieren.

### „Remote branch main not found" beim ersten `/sync`
Das Ziel-Repo ist leer und hat noch keinen `main`-Branch. Vor dem Start initialisieren:

**Option A — GitHub UI:** Repo öffnen und auf *Initialize this repository* klicken.

**Option B — Kommandozeile:**
```bash
git clone https://github.com/youruser/repo-en.git
cd repo-en
git commit --allow-empty -m "init"
git push origin main
```

Danach `/sync` erneut aufrufen.
