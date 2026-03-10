# GitTranslate

Automatisiertes LaTeX-Übersetzungssystem, das ein Quell-Git-Repository beobachtet und maschinell übersetzte Inhalte mithilfe eines lokalen LLMs über Ollama kontinuierlich in ein Ziel-Repository synchronisiert.

## Was es macht

- **Delta-Übersetzung** — bei jedem Push werden nur hinzugefügte/geänderte `.tex`-Dateien übersetzt; gelöschte Dateien werden aus dem Ziel-Repo entfernt
- **LaTeX-bewusst** — Gleichungen, Code-Listings, `\label{}`, `\ref{}` und Dateipfade werden nie verändert; nur menschenlesbarer Text wird an das LLM übergeben
- **Datenschutz-First** — die Übersetzung läuft vollständig lokal via [Ollama](https://ollama.com); keine Daten verlassen die eigene Infrastruktur
- **Flexible Auslösemodi** — Webhook (push-gesteuert) oder Polling (`POST /sync`), funktioniert mit selbst gehostetem Gitea und externen Anbietern (GitHub, GitLab)

## Schnellstart

**Voraussetzungen:** [Docker](https://www.docker.com/products/docker-desktop/) und [Ollama](https://ollama.com/download) auf dem Host-Rechner installiert.

```bash
ollama pull translategemma:4b
cp .env.example .env
# .env bearbeiten — SRC_GIT_URL, TARGET_GIT_URL, LLM_MODEL setzen
```

| Modus | Befehl | Wann verwenden |
|-------|--------|----------------|
| **Lokales Gitea** | `docker compose --profile local-git up -d` | Lokale Entwicklung / air-gapped |
| **Externes Git** | `docker compose up -d` | GitHub, GitLab, beliebiges Remote |

Beim lokalen Gitea-Modus: Ersteinrichtungsassistent unter `http://localhost:3000` abschließen, Repositories anlegen, Access Token generieren, in `.env` eintragen und den Worker neu bauen. Eine vollständige Anleitung befindet sich in `docs/SETUP_DE.md`.

Beim externen Git-Modus: Tokens in `.env` konfigurieren und die Übersetzung manuell auslösen:

```bash
curl -X POST http://localhost:8000/sync
```

## Dokumentation

| Datei | Beschreibung |
|-------|--------------|
| [docs/SETUP_DE.md](docs/SETUP_DE.md) | Vollständige Einrichtungsanleitung — Lokales Gitea und Externes Git |
| [docs/API_DE.md](docs/API_DE.md) | Worker HTTP-API-Referenz (`/webhook`, `/sync`, `/translate`) |
| [docs/THESIS_STRUCTURE_DE.md](docs/THESIS_STRUCTURE_DE.md) | LaTeX-Strukturleitfaden für Thesis-Autoren |

Englische Versionen: [docs/SETUP.md](docs/SETUP.md) · [docs/API.md](docs/API.md) · [docs/THESIS_STRUCTURE.md](docs/THESIS_STRUCTURE.md)

## Architektur

```
┌──────────────┐   Push / Webhook   ┌────────────────────────────────────────┐
│  Quell-Repo  │ ─────────────────> │  Worker  (FastAPI, localhost:8000)     │
│  (Deutsch)   │                    │  ├── latex_parser  (Chunk-Splitter)    │
└──────────────┘                    │  ├── llm_service   (Ollama-Client)     │
                                    │  └── git_service   (Clone / Push)      │
┌──────────────┐   Commit + Push    └────────────────────────────────────────┘
│  Ziel-Repo   │ <────────────────────────────────────────────────────────────
│  (Englisch)  │
└──────────────┘

Weitere Dienste (nur im lokalen Gitea-Modus):
  PostgreSQL  ←  Gitea (localhost:3000)
  Ollama läuft auf dem Host unter localhost:11434
```

**Worker-Dienst** (`worker/`):
- `main.py` — FastAPI-App mit `/` Health-Check, `/webhook`, `/sync` und `/translate`
- `core/config.py` — Pydantic `BaseSettings`; gesamte Konfiguration via `.env`
- `services/git_service.py` — Klont Repos, committed/pusht Ergebnisse; maskiert Tokens in Logs
- `services/latex_parser.py` — Teilt LaTeX in Präambel, übersetzbare Chunks und Postambel auf
- `services/llm_service.py` — Ruft `POST /api/generate` auf Ollama mit strukturiertem Prompt auf

## Lizenz

MIT — siehe [LICENSE](LICENSE).
