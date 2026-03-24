# GitTranslate

Automatisiertes LaTeX-Übersetzungssystem, das ein Quell-Git-Repository beobachtet und maschinell übersetzte Inhalte mithilfe eines lokalen LLMs über Ollama kontinuierlich in ein Ziel-Repository synchronisiert.

## Was es macht

- **Delta-Übersetzung** — bei jedem Push werden nur hinzugefügte/geänderte `.tex`-Dateien übersetzt; gelöschte Dateien werden aus dem Ziel-Repo entfernt
- **LaTeX-bewusst** — Gleichungen, Code-Listings, `\label{}`, `\ref{}` und Dateipfade werden nie verändert; nur menschenlesbarer Text wird an das LLM übergeben
- **Datenschutz-First** — die Übersetzung läuft vollständig lokal via [Ollama](https://ollama.com); keine Daten verlassen die eigene Infrastruktur
- **Flexible Auslösemodi** — Webhook (push-gesteuert) oder Polling (`POST /sync`), funktioniert mit GitHub, GitLab oder jedem Git-Anbieter

## Schnellstart

**Voraussetzungen:** [Ollama](https://ollama.com/download) auf dem Host-Rechner installiert.

```bash
ollama pull translategemma:4b
cp .env.example .env
# .env bearbeiten — SRC_GIT_URL, TARGET_GIT_URL, Tokens und LLM_MODEL setzen
```

### Mit Docker

Zusätzliche Voraussetzung: [Docker](https://www.docker.com/products/docker-desktop/)

In `.env` setzen: `LLM_API_URL=http://host.docker.internal:11434`

```bash
docker compose up -d
curl -X POST http://localhost:8000/sync
```

### Ohne Docker

Zusätzliche Voraussetzungen: Python 3.10+, Git

In `.env` setzen: `STATE_DIR=./state`

```bash
cd worker
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Dann in einem anderen Terminal:
```bash
curl -X POST http://localhost:8000/sync
```

Vollständige Anleitung: [docs/SETUP.md](docs/SETUP.md)

### Thesis-Struktur generieren

```bash
python init_thesis.py --title "Mein Titel" --author "Max Mustermann"
```

Erstellt ein `thesis-de/`-Verzeichnis mit der empfohlenen LaTeX-Struktur (siehe [docs/THESIS_STRUCTURE.md](docs/THESIS_STRUCTURE.md)).

## Dokumentation

| Datei | Beschreibung |
|-------|--------------|
| [docs/SETUP.md](docs/SETUP.md) | Vollständige Einrichtungsanleitung |
| [docs/API.md](docs/API.md) | Worker HTTP-API-Referenz (`/webhook`, `/sync`, `/translate`) |
| [docs/THESIS_STRUCTURE.md](docs/THESIS_STRUCTURE.md) | LaTeX-Strukturleitfaden für Thesis-Autoren |

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
