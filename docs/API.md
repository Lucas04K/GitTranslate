# GitTranslate Worker API

The GitTranslate worker exposes a small HTTP API for health checks, webhook-triggered translation, manual sync, and on-demand translation of specific files. An interactive Swagger UI is available at `http://localhost:8000/docs` and ReDoc at `http://localhost:8000/redoc`.

## Base URL

```
http://localhost:8000
```

(Port can be changed via Docker port mapping.)

## Authentication

Most endpoints require no authentication. The `/webhook` endpoint optionally validates an HMAC-SHA256 signature when `WEBHOOK_SECRET` is configured.

---

## Endpoints

### GET /

Health check. Returns current configuration and last-synced commit SHA.

**Response `200 OK`**

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

**Example**

```bash
curl http://localhost:8000/
```

---

### POST /webhook

Receives a Gitea push webhook, extracts added/modified/removed files from commit metadata, and enqueues a delta-translation job in the background.

**Request headers (optional)**

| Header | Description |
|---|---|
| `X-Hub-Signature-256` | `sha256=<hex>` HMAC signature of the raw JSON body |
| `X-Gitea-Signature` | Alternative header name accepted by Gitea |

If `WEBHOOK_SECRET` is set in `.env` and the signature is missing or invalid, the request is rejected with `401`.

**Request body** — raw Gitea push event JSON (sent automatically by Gitea).

**Response `200 OK`**

```json
{ "status": "accepted" }
```

**Error codes**

| Code | Reason |
|---|---|
| `400` | Invalid JSON payload |
| `401` | Missing or invalid HMAC signature |

**Example** (simulate a push event from a saved payload file)

```bash
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -d @payload.json
```

---

### POST /sync

Manually trigger a delta sync. The worker compares the source repo's current HEAD to the last-stored SHA, computes the diff, translates changed `.tex` files, and updates the stored SHA on success.

This is equivalent to the automatic poll that runs every `POLL_INTERVAL` seconds (if enabled).

**Request body** — none.

**Response `200 OK`**

```json
{ "status": "accepted" }
```

**Error codes**

| Code | Reason |
|---|---|
| `409` | A sync job is already running |

**Example**

```bash
curl -X POST http://localhost:8000/sync
```

---

### POST /translate

Clone both repos, translate a specific list of `.tex` files, and push. Useful for re-translating files without waiting for a commit or when the ignore file would otherwise suppress them.

**Request body** `application/json`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `paths` | `string[]` | yes | — | Relative paths of files to translate, e.g. `["chapters/01_intro.tex"]` |
| `use_ignore` | `boolean` | no | `false` | When `true`, paths matched by `.gittranslate-ignore` are silently skipped (same behaviour as `/webhook` and `/sync`). When `false` (default), the ignore file is bypassed and all listed paths are translated. |

**Response `200 OK`**

```json
{ "status": "accepted", "paths": ["chapters/01_intro.tex"] }
```

**Error codes**

| Code | Reason |
|---|---|
| `409` | A sync job is already running |
| `422` | Request body validation error (e.g. `paths` missing) |

**Examples**

Translate two files, bypassing `.gittranslate-ignore` (default):

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"paths": ["chapters/01_introduction.tex", "chapters/03_methodology.tex"]}'
```

Translate with ignore file respected:

```bash
curl -X POST http://localhost:8000/translate \
  -H "Content-Type: application/json" \
  -d '{"paths": ["chapters/01_introduction.tex"], "use_ignore": true}'
```

---

## .gittranslate-ignore

Place a `.gittranslate-ignore` file in the **source repo root** to exclude files from automatic translation. The format mirrors `.gitignore`:

- One glob pattern per line (matched with Python's `fnmatch`)
- Lines starting with `#` are comments
- Blank lines are ignored

**Example `.gittranslate-ignore`**

```
# Auto-generated files — do not translate
generated/*.tex
appendices/raw_data.tex

# Boilerplate unchanged between languages
preamble.tex
```

**Which endpoints respect it**

| Endpoint | Respects ignore file? |
|---|---|
| `POST /webhook` | Always yes |
| `POST /sync` | Always yes |
| `POST /translate` | Only when `use_ignore: true` is set |
