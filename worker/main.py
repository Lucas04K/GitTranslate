import asyncio
import os
import hmac
import hashlib
import json
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional
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

app = FastAPI(title="GitTranslate Worker")

# --- State (persisted across restarts via mounted volume) ---
STATE_FILE = Path("/app/state/sync_state.json")


def _load_last_sha() -> Optional[str]:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text()).get("last_sha")
    return None


def _save_last_sha(sha: str):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"last_sha": sha}))


# --- Shared delta logic ---
def _apply_delta(
    git: GitService,
    llm: LLMService,
    parser: LatexParser,
    src_dir: str,
    target_dir: str,
    changed_files: set,
    removed_files: set,
):
    tex_to_translate = {f for f in changed_files if f.endswith(".tex")}

    logger.info(f"Changed/new files total: {len(changed_files)}")
    logger.info(f"  of which .tex to translate: {len(tex_to_translate)}")
    logger.info(f"Deleted files: {len(removed_files)}")

    # Apply deletions
    for f in removed_files:
        target_file = os.path.join(target_dir, f)
        if os.path.exists(target_file):
            if os.path.isdir(target_file):
                shutil.rmtree(target_file)
            else:
                os.remove(target_file)
            logger.info(f"Deleted from target: {f}")

    # Copy changed files
    for f in changed_files:
        src_file = os.path.join(src_dir, f)
        target_file = os.path.join(target_dir, f)
        if os.path.exists(src_file):
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            shutil.copy2(src_file, target_file)

    # Translate .tex files
    for tex_file_rel_path in tex_to_translate:
        target_tex_file = os.path.join(target_dir, tex_file_rel_path)

        if not os.path.exists(target_tex_file):
            continue

        logger.info(f"Translating: {tex_file_rel_path}")

        with open(target_tex_file, "r", encoding="utf-8") as f:
            content = f.read()

        parsed = parser.parse_and_chunk(content)
        translated_chunks = []

        for i, chunk in enumerate(parsed["chunks"]):
            if not chunk.strip():
                translated_chunks.append(chunk)
                continue

            if parser.is_passthrough_chunk(chunk):
                logger.debug(f"Skipping passthrough chunk {i + 1} (math/code/structural).")
                translated_chunks.append(chunk)
                continue

            logger.debug(f"Translating paragraph {i + 1}/{len(parsed['chunks'])} in {tex_file_rel_path}...")
            try:
                translated_chunks.append(llm.translate_latex(chunk))
            except Exception as e:
                logger.error(f"Error on paragraph {i + 1}: {e}")
                translated_chunks.append(chunk)

        final_content = parser.reassemble(parsed["preamble"], translated_chunks, parsed["postamble"])

        with open(target_tex_file, "w", encoding="utf-8") as f:
            f.write(final_content)

    # Commit and push
    commit_msg = (
        f"Auto-Sync: updated {len(changed_files)} file(s), "
        f"translated {len(tex_to_translate)} .tex file(s)"
    )
    git.commit_and_push(target_dir, commit_msg)
    logger.info("Delta-sync completed successfully.")


# --- Webhook job ---
def _verify_webhook_secret(payload_bytes: bytes, sig_header: str) -> bool:
    if not settings.webhook_secret:
        return True
    secret = settings.webhook_secret.encode("utf-8")
    expected_hex = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    actual_hex = sig_header.removeprefix("sha256=") if sig_header else ""
    return hmac.compare_digest(expected_hex, actual_hex)


def process_translation_job(payload: dict):
    """Webhook-triggered job: sync only files listed in commit metadata."""
    logger.info("Starting translation job (delta mode)...")

    commits = payload.get("commits", [])
    if not commits:
        logger.info("No commits in payload (webhook test or branch creation). Aborting.")
        return

    changed_files = set()
    removed_files = set()

    for commit in commits:
        changed_files.update(commit.get("added", []))
        changed_files.update(commit.get("modified", []))
        removed_files.update(commit.get("removed", []))

    if not changed_files and not removed_files:
        logger.info("Nothing to sync.")
        return

    git = GitService()
    llm = LLMService()
    parser = LatexParser()

    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = os.path.join(temp_dir, "src")
        target_dir = os.path.join(temp_dir, "target")
        try:
            git.clone_src(src_dir)
            git.clone_target(target_dir)
            _apply_delta(git, llm, parser, src_dir, target_dir, changed_files, removed_files)
        except Exception as e:
            logger.error(f"Critical error in translation job: {e}")


# --- Sync job ---
def process_sync_job():
    """Poll-triggered job: compare HEAD SHA to stored SHA and sync if changed."""
    git = GitService()
    head_sha = git.get_head_sha()
    last_sha = _load_last_sha()

    if head_sha == last_sha:
        logger.info(f"Already up-to-date at {head_sha[:8]}. Nothing to do.")
        return

    logger.info(
        f"New commits detected: "
        f"{'first run' if last_sha is None else last_sha[:8]} → {head_sha[:8]}"
    )

    llm = LLMService()
    parser = LatexParser()

    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = os.path.join(temp_dir, "src")
        target_dir = os.path.join(temp_dir, "target")
        try:
            git.clone_src(src_dir)
            git.clone_target(target_dir)

            if last_sha is None:
                # First run: translate all tracked files
                all_files_output = git._run_command(["git", "ls-files"], cwd=src_dir)
                changed_files = set(all_files_output.splitlines())
                removed_files = set()
            else:
                changed_files, removed_files = git.get_diff(src_dir, last_sha, head_sha)

            _apply_delta(git, llm, parser, src_dir, target_dir, changed_files, removed_files)
            _save_last_sha(head_sha)
        except Exception as e:
            logger.error(f"Sync job failed: {e}")


# --- Sync lock + runner ---
_sync_lock = asyncio.Lock()


async def _run_locked_sync():
    async with _sync_lock:
        await asyncio.get_event_loop().run_in_executor(None, process_sync_job)


# --- Polling loop ---
@app.on_event("startup")
async def start_poller():
    if settings.poll_interval > 0:
        logger.info(f"Auto-polling enabled every {settings.poll_interval}s.")
        asyncio.create_task(_poll_loop())


async def _poll_loop():
    while True:
        await asyncio.sleep(settings.poll_interval)
        if not _sync_lock.locked():
            asyncio.create_task(_run_locked_sync())


# --- API Routes ---
@app.get("/")
async def health():
    return {
        "status": "online",
        "src": settings.src_git_url,
        "target": settings.target_git_url,
        "llm": f"{settings.llm_api_url} (model: {settings.llm_model})",
        "translation": f"{settings.source_lang} -> {settings.target_lang}",
        "poll_interval": settings.poll_interval or "disabled",
        "last_synced_sha": _load_last_sha(),
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    if settings.webhook_secret:
        sig = (
            request.headers.get("X-Hub-Signature-256")
            or request.headers.get("X-Gitea-Signature", "")
        )
        if not _verify_webhook_secret(raw_body, sig):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(raw_body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    background_tasks.add_task(process_translation_job, payload)
    return {"status": "accepted"}


@app.post("/sync")
async def sync(background_tasks: BackgroundTasks):
    if _sync_lock.locked():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    background_tasks.add_task(_run_locked_sync)
    return {"status": "accepted"}
