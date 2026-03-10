# GitTranslate Worker API

Der GitTranslate-Worker stellt eine kleine HTTP-API für Gesundheitschecks, Webhook-ausgelöste Übersetzungen, manuellen Sync sowie die bedarfsgesteuerte Übersetzung einzelner Dateien bereit. Eine interaktive Swagger-UI ist unter `http://localhost:8000/docs` und ReDoc unter `http://localhost:8000/redoc` erreichbar.

## Basis-URL

```
http://localhost:8000
```

(Der Port kann über das Docker-Port-Mapping geändert werden.)

## Authentifizierung

Die meisten Endpunkte erfordern keine Authentifizierung. Der `/webhook`-Endpunkt validiert optional eine HMAC-SHA256-Signatur, wenn `WEBHOOK_SECRET` konfiguriert ist.

---

## Endpunkte

### GET /

Gesundheitscheck. Gibt die aktuelle Konfiguration und den zuletzt synchronisierten Commit-SHA zurück.

**Antwort `200 OK`**

```json
{
  "status": "online",
  "src": "http://gitea:3000/user/repo-de.git",
  "target": "http://gitea:3000/user/repo-en.git",
  "llm": "http://host.docker.internal:11434 (model: translategemma:4b)",
  "translation": "de -> en",
  "poll_interval": 300,
  "last_synced_sha": "a1b2c3d4e5f6..."
}
```

**Beispiel**

```bash
curl http://localhost:8000/
```

---

### POST /webhook

Empfängt einen Gitea-Push-Webhook, extrahiert hinzugefügte/geänderte/entfernte Dateien aus den Commit-Metadaten und stellt einen Delta-Übersetzungsauftrag in die Hintergrundwarteschlange.

**Anfrage-Header (optional)**

| Header | Beschreibung |
|---|---|
| `X-Hub-Signature-256` | `sha256=<hex>` HMAC-Signatur des rohen JSON-Bodys (GitHub) |
| `X-Gitea-Signature` | `<hex>` HMAC-Signatur (Gitea) |
| `X-Gitlab-Token` | Rohes Klartext-Geheimnis (GitLab) — Vergleich mit konstantem Zeitaufwand |

Wenn `WEBHOOK_SECRET` in `.env` gesetzt ist und die Signatur/das Token fehlt oder ungültig ist, wird die Anfrage mit `401` abgelehnt.

**Anfrage-Body** — roher Gitea-Push-Event-JSON (wird automatisch von Gitea gesendet).

**Antwort `200 OK`**

```json
{ "status": "accepted" }
```

**Fehlercodes**

| Code | Ursache |
|---|---|
| `400` | Ungültige JSON-Nutzlast |
| `401` | Fehlende oder ungültige HMAC-Signatur |

**Beispiel** (Push-Event aus einer gespeicherten Payload-Datei simulieren)

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d @payload.json
```

---

### POST /sync

Löst einen Delta-Sync manuell aus. Der Worker vergleicht den aktuellen HEAD des Quell-Repos mit dem zuletzt gespeicherten SHA, berechnet den Diff, übersetzt geänderte `.tex`-Dateien und aktualisiert bei Erfolg den gespeicherten SHA.

Dies entspricht dem automatischen Poll, der alle `POLL_INTERVAL` Sekunden ausgeführt wird (sofern aktiviert).

**Anfrage-Body** — keiner.

**Antwort `200 OK`**

```json
{ "status": "accepted" }
```

**Fehlercodes**

| Code | Ursache |
|---|---|
| `409` | Ein Sync-Auftrag läuft bereits |

**Beispiel**

```bash
curl -X POST http://localhost:8000/sync
```

---

### POST /translate

Klont beide Repos, übersetzt eine bestimmte Liste von `.tex`-Dateien und pusht das Ergebnis. Nützlich, um Dateien neu zu übersetzen, ohne auf einen Commit zu warten oder wenn die Ignore-Datei sie andernfalls unterdrücken würde.

**Anfrage-Body** `application/json`

| Feld | Typ | Pflicht | Standard | Beschreibung |
|---|---|---|---|---|
| `paths` | `string[]` | ja | — | Relative Pfade der zu übersetzenden Dateien, z. B. `["chapters/01_intro.tex"]` |
| `use_ignore` | `boolean` | nein | `false` | Wenn `true`, werden Pfade, die von `.gittranslate-ignore` erfasst werden, stillschweigend übersprungen (gleiches Verhalten wie `/webhook` und `/sync`). Wenn `false` (Standard), wird die Ignore-Datei umgangen und alle angegebenen Pfade werden übersetzt. |

**Antwort `200 OK`**

```json
{ "status": "accepted", "paths": ["chapters/01_intro.tex"] }
```

**Fehlercodes**

| Code | Ursache |
|---|---|
| `409` | Ein Sync-Auftrag läuft bereits |
| `422` | Validierungsfehler im Anfrage-Body (z. B. `paths` fehlt) |

**Beispiele**

Zwei Dateien übersetzen, `.gittranslate-ignore` umgehen (Standard):

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"paths": ["chapters/01_introduction.tex", "chapters/03_methodology.tex"]}'
```

Mit Berücksichtigung der Ignore-Datei übersetzen:

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"paths": ["chapters/01_introduction.tex"], "use_ignore": true}'
```

---

## .gittranslate-ignore

Lege eine `.gittranslate-ignore`-Datei im **Wurzelverzeichnis des Quell-Repos** ab, um Dateien von der automatischen Übersetzung auszuschließen. Das Format orientiert sich an `.gitignore`:

- Ein Glob-Muster pro Zeile (abgeglichen mit Pythons `fnmatch`)
- Zeilen, die mit `#` beginnen, sind Kommentare
- Leerzeilen werden ignoriert

**Beispiel `.gittranslate-ignore`**

```
# Automatisch generierte Dateien — nicht übersetzen
generated/*.tex
appendices/raw_data.tex

# Vorlagen, die in beiden Sprachen identisch sind
preamble.tex
```

**Welche Endpunkte die Ignore-Datei berücksichtigen**

| Endpunkt | Berücksichtigt Ignore-Datei? |
|---|---|
| `POST /webhook` | Immer ja |
| `POST /sync` | Immer ja |
| `POST /translate` | Nur wenn `use_ignore: true` gesetzt ist |
