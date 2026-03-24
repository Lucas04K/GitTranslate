# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GitTranslate is an automated LaTeX translation system that watches a source Git repository and syncs translated content to a target repository using a local LLM via Ollama. It works with any Git provider (GitHub, GitLab, Gitea, etc.) and is triggered by webhooks or manual sync.

## Common Commands

```bash
# Start with Docker
docker compose up -d

# Start without Docker
cd worker && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# View worker logs (Docker)
docker compose logs -f worker

# Rebuild and restart worker after code changes
docker compose up -d --build worker

# Health check
curl http://localhost:8000/

# Manually trigger translation
curl -X POST http://localhost:8000/sync
```

There is no test suite currently. Manual testing is done by pushing to the source repo or calling `POST /sync` and monitoring logs.

## Architecture

**Worker** (`localhost:8000`) — FastAPI service that processes translations. Can run via Docker (`docker compose up -d`) or directly with Python (`uvicorn`).

Ollama runs on the host at `localhost:11434`. When running inside Docker, the worker reaches Ollama via `host.docker.internal:11434`.

**Worker service** (`worker/`):
- `main.py` — FastAPI app with `/` (health), `/webhook`, `/sync`, and `/translate` endpoints. Webhook handler spawns a background task immediately so the HTTP response is not blocked.
- `core/config.py` — Pydantic BaseSettings; all config via `.env` file.
- `services/git_service.py` — Clones repos and commits/pushes results. Masks tokens in logs.
- `services/latex_parser.py` — Splits LaTeX into preamble, translatable body chunks (split on `\n\n`), and postamble. Preserves all whitespace for lossless reconstruction.
- `services/llm_service.py` — Calls Ollama's `POST /api/generate` with a structured translation prompt that instructs the model to never modify LaTeX commands.

## Translation Workflow (Delta Mode)

On each webhook push or `/sync` call:
1. Extract added/modified/removed `.tex` files from commit metadata (webhook) or git diff (sync)
2. Clone both source and target repos into a temp directory
3. Apply deletions to target repo
4. Copy changed files from source to target (preserving directory structure)
5. For each changed `.tex` file: parse → translate chunks via Ollama → reassemble → write
6. Commit and push target repo with a summary message

If a chunk fails to translate, the original text is kept and processing continues.

## Configuration

Copy `.env.example` to `.env`. Required variables:
- `SRC_GIT_URL` / `SRC_GIT_TOKEN` — source repo URL and access token
- `TARGET_GIT_URL` / `TARGET_GIT_TOKEN` — target repo URL and access token
- `LLM_MODEL` — e.g., `translategemma:4b`

Optional: `LLM_API_URL` (default: `http://localhost:11434`, use `http://host.docker.internal:11434` for Docker), `LLM_TIMEOUT` (default: `120`), `LOG_LEVEL` (default: `INFO`), `POLL_INTERVAL` (default: `0`), `WEBHOOK_SECRET`, `STATE_DIR` (default: `/app/state`, use `./state` without Docker).

See `docs/SETUP.md` for full setup guide.
