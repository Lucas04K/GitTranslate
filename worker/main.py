import os
import shutil
import tempfile
import logging
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks

from core.config import settings
from services.git_service import GitService
from services.llm_service import LLMService
from services.latex_parser import LatexParser

# --- Logging Setup ---
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="TexSync Worker")


# --- Die Orchestrierungs-Logik (DELTA MODUS) ---
def process_translation_job(payload: dict):
    """
    Hauptjob: Klont Repos, synchronisiert NUR geänderte Dateien und übersetzt neue/geänderte .tex Dateien.
    """
    logger.info("Starte Übersetzungs-Job (Delta-Modus)...")

    # 1. Gitea Payload analysieren
    commits = payload.get("commits", [])
    if not commits:
        logger.info("Keine Commits im Payload gefunden (Webhook-Test oder Branch-Erstellung). Breche ab.")
        return

    changed_files = set()
    removed_files = set()

    # Sammle alle geänderten Dateien aus allen Commits in diesem Push
    for commit in commits:
        changed_files.update(commit.get("added", []))
        changed_files.update(commit.get("modified", []))
        removed_files.update(commit.get("removed", []))

    # Filtere heraus, welche davon .tex Dateien sind
    tex_to_translate = {f for f in changed_files if f.endswith(".tex")}

    logger.info(f"Geänderte/Neue Dateien gesamt: {len(changed_files)}")
    logger.info(f"Davon zu übersetzende .tex Dateien: {len(tex_to_translate)}")
    logger.info(f"Gelöschte Dateien: {len(removed_files)}")

    # Wenn sich absolut nichts Relevantes geändert hat, sind wir hier fertig.
    if not changed_files and not removed_files:
        logger.info("Nichts zu synchronisieren.")
        return

    git = GitService()
    llm = LLMService()
    parser = LatexParser()

    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = os.path.join(temp_dir, "src")
        target_dir = os.path.join(temp_dir, "target")

        try:
            # 2. Beide Repositories klonen
            git.clone_repo(settings.src_repo_path, src_dir)
            git.clone_repo(settings.target_repo_path, target_dir)

            # 3. Gelöschte Dateien im Ziel-Repo ebenfalls löschen
            for f in removed_files:
                target_file = os.path.join(target_dir, f)
                if os.path.exists(target_file):
                    if os.path.isdir(target_file):
                        shutil.rmtree(target_file)
                    else:
                        os.remove(target_file)
                    logger.info(f"Datei im Ziel gelöscht: {f}")

            # 4. NUR die geänderten/neuen Dateien von src nach target kopieren
            # Das ist wichtig, damit z.B. auch neue Bilder (.png) drüben ankommen!
            for f in changed_files:
                src_file = os.path.join(src_dir, f)
                target_file = os.path.join(target_dir, f)

                if os.path.exists(src_file):
                    # Falls die Datei in einem neuen Unterordner liegt, Ordnerstruktur im Ziel bauen
                    os.makedirs(os.path.dirname(target_file), exist_ok=True)
                    shutil.copy2(src_file, target_file)

            # 5. NUR die frisch geänderten .tex Dateien parsen und übersetzen
            for tex_file_rel_path in tex_to_translate:
                target_tex_file = os.path.join(target_dir, tex_file_rel_path)

                if not os.path.exists(target_tex_file):
                    continue

                logger.info(f"Übersetze Datei: {tex_file_rel_path}")

                with open(target_tex_file, "r", encoding="utf-8") as f:
                    content = f.read()

                parsed = parser.parse_and_chunk(content)
                translated_chunks = []

                for i, chunk in enumerate(parsed["chunks"]):
                    if not chunk.strip():
                        translated_chunks.append(chunk)
                        continue

                    logger.debug(f"Übersetze Absatz {i + 1}/{len(parsed['chunks'])} in {tex_file_rel_path}...")
                    try:
                        translated_text = llm.translate_latex(chunk)
                        translated_chunks.append(translated_text)
                    except Exception as e:
                        logger.error(f"Fehler bei Absatz {i + 1}: {e}")
                        translated_chunks.append(chunk)

                final_content = parser.reassemble(parsed["preamble"], translated_chunks, parsed["postamble"])

                with open(target_tex_file, "w", encoding="utf-8") as f:
                    f.write(final_content)

            # 6. Änderungen pushen
            commit_msg = f"Auto-Sync: Aktualisiert ({len(changed_files)} Dateien), Übersetzt ({len(tex_to_translate)} .tex)"
            git.commit_and_push(target_dir, commit_msg)
            logger.info("Delta-Sync erfolgreich abgeschlossen! 🎉")

        except Exception as e:
            logger.error(f"Kritischer Fehler im Übersetzungs-Job: {e}")


# --- API Routen ---
@app.get("/")
async def health():
    return {
        "status": "online",
        "gitea": "configured" if settings.gitea_token else "missing_token",
        "repos": f"{settings.src_repo_path} -> {settings.target_repo_path}",
        "ollama": f"{settings.ollama_host} (Model: {settings.ollama_model})"
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    if not settings.gitea_token:
        raise HTTPException(status_code=500, detail="Worker nicht vollständig konfiguriert")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiges JSON Payload")

    background_tasks.add_task(process_translation_job, payload)
    return {"status": "accepted", "message": "Delta-Translation job started in background"}