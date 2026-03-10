# GitTranslate Setup Guide

GitTranslate supports two usage modes:

| Mode | Git provider | When to use |
|------|-------------|-------------|
| **A – Local** | Gitea (self-hosted, via Docker) | Local development / air-gapped setup |
| **B – External** | GitHub, GitLab, any Gitea instance | Production / existing repos |

Both modes require Ollama running on the host machine.

---

## Prerequisites: Docker

1. Install Docker Desktop (includes Docker Compose):
   https://www.docker.com/products/docker-desktop/
   - macOS / Windows: download and run the installer
   - Linux: follow the [Engine install guide](https://docs.docker.com/engine/install/) and install the Compose plugin separately
2. Verify both are available:
   ```bash
   docker --version
   docker compose version
   ```

---

## Prerequisites: Ollama

1. Install Ollama: https://ollama.com/download
2. Pull a model:
   ```bash
   ollama pull translategemma:4b
   ```
3. Verify it's running: `curl http://localhost:11434/`

---

## Mode A — Local Gitea + Ollama

### 1. Configure `.env`

Copy the example and fill in the values:
```bash
cp .env.example .env
```

Set at minimum:
```
SRC_GIT_URL=http://gitea:3000/admin/repo-de
TARGET_GIT_URL=http://gitea:3000/admin/repo-en
LLM_MODEL=translategemma:4b
```
Leave `SRC_GIT_TOKEN` / `TARGET_GIT_TOKEN` blank for now — you'll fill them in after Gitea starts.

### 2. Start all services

```bash
docker compose --profile local-git up -d
```

### 3. Gitea first-run wizard

Open http://localhost:3000 (or `GITEA_HTTP_PORT` if changed).

- The first account you create becomes the admin.
- Accept all database defaults (already configured via environment).

### 4. Create repositories

In Gitea's web UI:
- Create `repo-de` (source, German)
- Create `repo-en` (target, English)

Or via API:
```bash
curl -s -X POST http://localhost:3000/api/v1/user/repos \
  -u admin:admin123 -H "Content-Type: application/json" \
  -d '{"name":"repo-de","private":false}'
```

### 5. Generate an access token

**Gitea UI → User Settings → Applications → Generate Token**

Paste the token into `.env`:
```
SRC_GIT_TOKEN=<token>
TARGET_GIT_TOKEN=<token>
```

### 6. Rebuild the worker

```bash
docker compose --profile local-git up -d --build worker
```

### 7. Configure the webhook

In Gitea: **repo-de → Settings → Webhooks → Add Webhook → Gitea**

- **Target URL**: `http://worker:8000/webhook`
  (use `http://host.docker.internal:8000/webhook` if worker is outside Docker)
- **Content type**: `application/json`
- **Secret**: optionally set a value and add it to `.env` as `WEBHOOK_SECRET`
- **Trigger**: Push events

### 8. Test

Push a `.tex` file to `repo-de`. Watch logs:
```bash
docker compose logs -f worker
```

---

## Mode B — External Git (GitHub / GitLab) + Ollama

### 1. Configure `.env`

```bash
cp .env.example .env
```

Set the full HTTPS URLs and personal access tokens for your repos:
```
SRC_GIT_URL=https://github.com/youruser/repo-de
SRC_GIT_TOKEN=ghp_xxxxxxxxxxxx

TARGET_GIT_URL=https://github.com/youruser/repo-en
TARGET_GIT_TOKEN=ghp_xxxxxxxxxxxx

LLM_MODEL=translategemma:4b
```

**GitHub**: Settings → Developer settings → Personal access tokens → Fine-grained
Required scopes: `Contents` (read for source, read+write for target)

**GitLab**: User Settings → Access Tokens → `read_repository` + `write_repository`

### 2. Start only the worker

```bash
docker compose up -d
```

No Gitea or database will start (they require `--profile local-git`).

### 3. Trigger translation with `/sync`

No webhook or public URL needed. Use `POST /sync` to check for new commits and translate:

```bash
# One-off manual sync
curl -X POST http://localhost:8000/sync
```

The worker compares the current HEAD SHA against the last processed SHA (stored in a Docker volume). On the first call it translates all `.tex` files in the source repo. Subsequent calls only process changed files.

### 4. Automate syncing

**Option A — cron job** (e.g. every 5 minutes):
```
*/5 * * * * curl -s -X POST http://localhost:8000/sync
```

**Option B — built-in polling**: set `POLL_INTERVAL` in `.env` (seconds):
```
POLL_INTERVAL=300
```
The worker will poll automatically on startup, no external scheduler needed.

**Option C — webhooks** (requires a public URL / tunnel):

For local development, use a tunnel (e.g. [ngrok](https://ngrok.com)):
```bash
ngrok http 8000
# → https://abc123.ngrok.io
```

**GitHub**: repo → Settings → Webhooks → Add webhook
- **Payload URL**: `https://abc123.ngrok.io/webhook`
- **Content type**: `application/json`
- **Secret**: set a value here and in `.env` as `WEBHOOK_SECRET`
- **Events**: Just the push event

**GitLab**: repo → Settings → Webhooks
- **URL**: `https://abc123.ngrok.io/webhook`
- **Secret token**: same as `WEBHOOK_SECRET`
- **Trigger**: Push events

---

## Webhook Secret Validation

Set `WEBHOOK_SECRET` in `.env` and use the same value in your Git provider's webhook settings.

GitTranslate accepts both:
- **GitHub format**: `X-Hub-Signature-256: sha256=<hex>`
- **Gitea format**: `X-Gitea-Signature: <hex>`

Invalid requests return HTTP 401.

---

## Configuring Language Pair

The source and target languages are configurable:
```
SOURCE_LANG=German
TARGET_LANG=English
```

Change these to any language pair your LLM supports.

---

## Health Check

```bash
curl http://localhost:8000/
```

Returns a JSON summary of current configuration.

---

## Troubleshooting

### Worker crashes on startup with "Field required" validation errors
The Docker image is stale. Rebuild it after any code or config change:
```bash
docker compose up -d --build worker
```

### 403 "Write access to repository not granted" on `/sync`
Your token doesn't have the required permissions. For GitHub fine-grained PATs:

- **Source repo** (`repo-de`): `Contents` → **Read**
- **Target repo** (`repo-en`): `Contents` → **Read and Write**

Go to: GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Edit your token.

> Tip: if the token appears in logs, regenerate it immediately.

### "Remote branch main not found" on first `/sync`
The target repo is empty and has no `main` branch yet. Initialise it before starting:

**Option A — GitHub UI:** open the repo and click *Initialize this repository*.

**Option B — command line:**
```bash
git clone https://github.com/youruser/repo-en.git
cd repo-en
git commit --allow-empty -m "init"
git push origin main
```

Then trigger `/sync` again.
