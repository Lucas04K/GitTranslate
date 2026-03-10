# GitTranslate

Automated LaTeX translation system that watches a source Git repository and continuously syncs machine-translated content to a target repository using a local LLM via Ollama.

## What it does

- **Delta translation** — on every push, only added/modified `.tex` files are translated; deleted files are removed from the target
- **LaTeX-aware** — equations, code listings, `\label{}`, `\ref{}`, and file paths are never modified; only human-readable text is sent to the LLM
- **Privacy-first** — translation runs entirely on your machine via [Ollama](https://ollama.com); no data leaves your infrastructure
- **Flexible trigger modes** — webhook (push-driven) or polling (`POST /sync`), works with self-hosted Gitea and external providers (GitHub, GitLab)

## Quick start

**Prerequisites:** [Docker](https://www.docker.com/products/docker-desktop/) and [Ollama](https://ollama.com/download) installed on the host machine.

```bash
ollama pull translategemma:4b
cp .env.example .env
# Edit .env — set SRC_GIT_URL, TARGET_GIT_URL, LLM_MODEL
```

| Mode | Command | When to use |
|------|---------|-------------|
| **Local Gitea** | `docker compose --profile local-git up -d` | Local dev / air-gapped |
| **External Git** | `docker compose up -d` | GitHub, GitLab, any remote |

For Local Gitea, complete the first-run wizard at `http://localhost:3000`, create your repos, generate an access token, add it to `.env`, then rebuild the worker. See `docs/SETUP.md` for the full walkthrough.

For External Git, configure tokens in `.env` and trigger translation manually:

```bash
curl -X POST http://localhost:8000/sync
```

## Documentation

| File | Description |
|------|-------------|
| [docs/SETUP.md](docs/SETUP.md) | Full setup guide — Local Gitea and External Git modes |
| [docs/API.md](docs/API.md) | Worker HTTP API reference (`/webhook`, `/sync`, `/translate`) |
| [docs/THESIS_STRUCTURE.md](docs/THESIS_STRUCTURE.md) | LaTeX structure guide for thesis authors |

German versions: [docs/SETUP_DE.md](docs/SETUP_DE.md) · [docs/API_DE.md](docs/API_DE.md) · [docs/THESIS_STRUCTURE_DE.md](docs/THESIS_STRUCTURE_DE.md)

## Architecture

```
┌─────────────┐   push / webhook   ┌────────────────────────────────────────┐
│  Source repo │ ─────────────────> │  Worker  (FastAPI, localhost:8000)     │
│  (German)   │                    │  ├── latex_parser  (chunk splitter)    │
└─────────────┘                    │  ├── llm_service   (Ollama client)     │
                                   │  └── git_service   (clone / push)      │
┌─────────────┐   commit + push    └────────────────────────────────────────┘
│  Target repo │ <────────────────────────────────────────────────────────────
│  (English)  │
└─────────────┘

Supporting services (Local Gitea mode only):
  PostgreSQL  ←  Gitea (localhost:3000)
  Ollama runs on host at localhost:11434
```

**Worker service** (`worker/`):
- `main.py` — FastAPI app with `/` health, `/webhook`, `/sync`, and `/translate` endpoints
- `core/config.py` — Pydantic `BaseSettings`; all config via `.env`
- `services/git_service.py` — Clones repos, commits/pushes results; masks tokens in logs
- `services/latex_parser.py` — Splits LaTeX into preamble, translatable chunks, postamble
- `services/llm_service.py` — Calls `POST /api/generate` on Ollama with a structured prompt

## License

MIT — see [LICENSE](LICENSE).
