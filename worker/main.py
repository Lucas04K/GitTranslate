import asyncio
import fnmatch
import os
import hmac
import hashlib
import secrets
import json
import shutil
import tempfile
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from pydantic import BaseModel, Field

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

app = FastAPI(
    title="GitTranslate Worker",
    version="1.0.0",
    description=(
        "Watches a source LaTeX repo (German) and automatically translates "
        "changed `.tex` files into a target repo (English) via a local LLM.\n\n"
        "**Swagger UI:** `/docs` · **ReDoc:** `/redoc`"
    ),
)

# --- State (persisted across restarts via mounted volume) ---
STATE_FILE = Path(settings.state_dir) / "sync_state.json"


def _load_state() -> dict:
    """Load sync state. Backward-compatible with old format."""
    if STATE_FILE.exists():
        data = json.loads(STATE_FILE.read_text())
        # Migrate old format: {"last_sha": "..."} → add empty files dict
        if "files" not in data:
            data["files"] = {}
        return data
    return {"last_sha": None, "files": {}}


def _save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def _set_file_state(
    state: dict, path: str, status: str, src_hash: str, failed_chunks: list[int]
):
    state["files"][path] = {
        "status": status,
        "src_hash": src_hash,
        "failed_chunks": failed_chunks,
    }


# --- Ignore file helpers ---
def _load_ignore_patterns(src_dir: Path) -> list[str]:
    """Read .gittranslate-ignore from the source repo root. Returns list of glob patterns."""
    ignore_file = src_dir / ".gittranslate-ignore"
    if not ignore_file.exists():
        return []
    patterns = []
    for line in ignore_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            patterns.append(line)
    return patterns


def _is_ignored(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, p) for p in patterns)


# --- Shared delta logic ---
def _apply_delta(
    git: GitService,
    llm: LLMService,
    parser: LatexParser,
    src_dir: str,
    target_dir: str,
    changed_files: set,
    removed_files: set,
    state: dict,
    apply_ignore: bool = True,
    commit_msg: Optional[str] = None,
) -> dict:
    tex_to_translate = {f for f in changed_files if f.endswith(".tex")}

    # .gittranslate-ignore only skips translation, files are still copied
    if apply_ignore:
        ignore_patterns = _load_ignore_patterns(Path(src_dir))
        if ignore_patterns:
            before = len(tex_to_translate)
            tex_to_translate = {f for f in tex_to_translate if not _is_ignored(f, ignore_patterns)}
            skipped = before - len(tex_to_translate)
            if skipped:
                logger.info("Skipped %d file(s) from translation due to .gittranslate-ignore", skipped)

    # Determine which tex files are retry-only (source unchanged, only failed chunks)
    retry_only_tex: dict[str, list[int]] = {}
    for f in list(tex_to_translate):
        fstate = state["files"].get(f)
        if fstate and fstate["status"] in ("partial", "failed"):
            src_file = os.path.join(src_dir, f)
            if os.path.exists(src_file):
                with open(src_file, "r", encoding="utf-8") as fh:
                    current_hash = hashlib.sha256(fh.read().encode()).hexdigest()
                if fstate["src_hash"] == current_hash:
                    retry_only_tex[f] = fstate.get("failed_chunks", [])

    logger.info(f"Changed/new files total: {len(changed_files)}")
    logger.info(f"  of which .tex to translate: {len(tex_to_translate)}")
    logger.info(f"  of which retry-only (failed chunks): {len(retry_only_tex)}")
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
        # Remove from state tracking
        state["files"].pop(f, None)

    # Copy changed files (skip retry-only tex files to preserve partial translations)
    for f in changed_files:
        if f in retry_only_tex:
            continue
        src_file = os.path.join(src_dir, f)
        target_file = os.path.join(target_dir, f)
        if os.path.exists(src_file):
            os.makedirs(os.path.dirname(target_file), exist_ok=True)
            shutil.copy2(src_file, target_file)

    # Translate .tex files
    for tex_file_rel_path in tex_to_translate:
        target_tex_file = os.path.join(target_dir, tex_file_rel_path)
        src_tex_file = os.path.join(src_dir, tex_file_rel_path)

        if not os.path.exists(target_tex_file):
            continue

        logger.info(f"Translating: {tex_file_rel_path}")

        # Compute source hash for state tracking
        with open(src_tex_file, "r", encoding="utf-8") as f:
            src_content = f.read()
        src_hash = hashlib.sha256(src_content.encode()).hexdigest()

        # For retry-only files: read target (has partial translations), source chunks separately
        chunks_to_retry: set[int] | None = None
        source_parsed: dict | None = None
        if tex_file_rel_path in retry_only_tex:
            chunks_to_retry = set(retry_only_tex[tex_file_rel_path])
            source_parsed = parser.parse_and_chunk(src_content)
            with open(target_tex_file, "r", encoding="utf-8") as f:
                content = f.read()
            logger.info(f"  Retry mode: re-translating {len(chunks_to_retry)} failed chunk(s)")
        else:
            with open(target_tex_file, "r", encoding="utf-8") as f:
                content = f.read()

        parsed = parser.parse_and_chunk(content)
        translated_chunks = []
        failed_chunk_indices: list[int] = []

        for i, chunk in enumerate(parsed["chunks"]):
            if not chunk.strip():
                translated_chunks.append(chunk)
                continue

            if parser.is_passthrough_chunk(chunk):
                logger.debug(f"Skipping passthrough chunk {i + 1} (math/code/structural).")
                translated_chunks.append(chunk)
                continue

            # In retry mode, skip chunks that already succeeded
            if chunks_to_retry is not None and i not in chunks_to_retry:
                translated_chunks.append(chunk)
                continue

            # Use source chunk as LLM input (for retry: from source_parsed)
            input_chunk = (
                source_parsed["chunks"][i]
                if source_parsed and i < len(source_parsed["chunks"])
                else chunk
            )

            logger.debug(f"Translating paragraph {i + 1}/{len(parsed['chunks'])} in {tex_file_rel_path}...")
            try:
                protected, store = parser.protect(input_chunk)
                translated = llm.translate_latex(protected)
                translated_chunks.append(parser.restore(translated, store))
            except Exception as e:
                logger.error(f"Error on paragraph {i + 1}: {e}")
                translated_chunks.append(chunk)
                failed_chunk_indices.append(i)

        final_content = parser.reassemble(parsed["preamble"], translated_chunks, parsed["postamble"])

        with open(target_tex_file, "w", encoding="utf-8") as f:
            f.write(final_content)

        # Update per-file state
        status = "success" if not failed_chunk_indices else "partial"
        _set_file_state(state, tex_file_rel_path, status, src_hash, failed_chunk_indices)
        if failed_chunk_indices:
            logger.warning(
                f"  {tex_file_rel_path}: {len(failed_chunk_indices)} chunk(s) failed — marked as partial"
            )

    # Commit and push
    if commit_msg is None:
        commit_msg = (
            f"Auto-Sync: updated {len(changed_files)} file(s), "
            f"translated {len(tex_to_translate)} .tex file(s)"
        )
    git.commit_and_push(target_dir, commit_msg)
    logger.info("Delta-sync completed successfully.")
    return state


# --- Webhook job ---
def _verify_webhook_secret(payload_bytes: bytes, request_headers) -> bool:
    if not settings.webhook_secret:
        return True

    # GitLab: X-Gitlab-Token is the raw secret (plain equality, no HMAC)
    gitlab_token = request_headers.get("X-Gitlab-Token")
    if gitlab_token is not None:
        return secrets.compare_digest(gitlab_token, settings.webhook_secret)

    # GitHub / Gitea: HMAC-SHA256 signature
    sig = (
        request_headers.get("X-Hub-Signature-256")
        or request_headers.get("X-Gitea-Signature", "")
    )
    secret = settings.webhook_secret.encode("utf-8")
    expected_hex = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    actual_hex = sig.removeprefix("sha256=") if sig else ""
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

    state = _load_state()

    # Add retry files (partial/failed from previous runs)
    for path, fstate in state["files"].items():
        if fstate["status"] in ("partial", "failed") and path not in changed_files:
            changed_files.add(path)

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
            state = _apply_delta(git, llm, parser, src_dir, target_dir, changed_files, removed_files, state)
            _save_state(state)
        except Exception as e:
            logger.error(f"Critical error in translation job: {e}")


# --- Sync job ---
def process_sync_job():
    """Poll-triggered job: compare HEAD SHA to stored SHA and sync if changed."""
    git = GitService()
    head_sha = git.get_head_sha()
    state = _load_state()
    last_sha = state.get("last_sha")

    has_new_commits = head_sha != last_sha
    # Check for files needing retry even if no new commits
    retry_files = {
        path for path, fstate in state["files"].items()
        if fstate["status"] in ("partial", "failed")
    }

    if not has_new_commits and not retry_files:
        logger.info(f"Already up-to-date at {head_sha[:8]}. Nothing to do.")
        return

    if has_new_commits:
        logger.info(
            f"New commits detected: "
            f"{'first run' if last_sha is None else last_sha[:8]} → {head_sha[:8]}"
        )
    if retry_files:
        logger.info(f"Retrying {len(retry_files)} previously incomplete file(s)")

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
                if has_new_commits:
                    changed_files, removed_files = git.get_diff(src_dir, last_sha, head_sha)
                else:
                    changed_files, removed_files = set(), set()

            # Merge in retry files
            changed_files |= retry_files

            state = _apply_delta(git, llm, parser, src_dir, target_dir, changed_files, removed_files, state)
            state["last_sha"] = head_sha
            _save_state(state)
        except Exception as e:
            logger.error(f"Sync job failed: {e}")


# --- Manual translate job ---
def _translate_specific(paths: list[str], use_ignore: bool = False):
    """Translate specific paths on demand."""
    logger.info("Starting manual translation job for %d file(s)...", len(paths))
    git = GitService()
    llm = LLMService()
    parser = LatexParser()
    state = _load_state()

    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = os.path.join(temp_dir, "src")
        target_dir = os.path.join(temp_dir, "target")
        try:
            git.clone_src(src_dir)
            git.clone_target(target_dir)
            state = _apply_delta(
                git, llm, parser,
                src_dir, target_dir,
                changed_files=set(paths),
                removed_files=set(),
                state=state,
                apply_ignore=use_ignore,
                commit_msg=f"GitTranslate: manual translate {len(paths)} file(s)",
            )
            _save_state(state)
        except Exception as e:
            logger.error(f"Manual translate job failed: {e}")


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


# --- Request / Response models ---
class TranslateRequest(BaseModel):
    paths: list[str] = Field(
        ...,
        description="Relative paths of .tex files to translate (e.g. ['chapters/01_intro.tex'])",
        examples=[["chapters/01_introduction.tex", "chapters/03_methodology.tex"]],
    )
    use_ignore: bool = Field(
        False,
        description=(
            "When True, paths listed in .gittranslate-ignore are silently skipped, "
            "just like /webhook and /sync. Default False — all listed paths are translated."
        ),
    )


# --- API Routes ---
@app.get("/")
async def health():
    state = _load_state()
    return {
        "status": "online",
        "src": settings.src_git_url,
        "target": settings.target_git_url,
        "llm": f"{settings.llm_api_url} (model: {settings.llm_model})",
        "translation": f"{settings.source_lang} -> {settings.target_lang}",
        "poll_interval": settings.poll_interval or "disabled",
        "last_synced_sha": state.get("last_sha"),
    }


@app.get("/status", summary="Translation status per file")
async def status():
    state = _load_state()
    file_states = state.get("files", {})
    return {
        "last_sha": state.get("last_sha"),
        "total_files": len(file_states),
        "success": sum(1 for f in file_states.values() if f["status"] == "success"),
        "partial": sum(1 for f in file_states.values() if f["status"] == "partial"),
        "failed": sum(1 for f in file_states.values() if f["status"] == "failed"),
        "files": file_states,
    }


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    raw_body = await request.body()

    if not _verify_webhook_secret(raw_body, request.headers):
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


@app.post("/hard-reset", summary="Wipe state and re-translate everything from scratch")
async def hard_reset(background_tasks: BackgroundTasks):
    """
    Reset all translation state and re-translate every `.tex` file from scratch.
    Clones source, overwrites the entire target repo content, translates all `.tex` files, and pushes.
    """
    if _sync_lock.locked():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    background_tasks.add_task(_run_locked_hard_reset)
    return {"status": "accepted", "message": "Hard reset started — all files will be re-translated"}


async def _run_locked_hard_reset():
    async with _sync_lock:
        await asyncio.get_event_loop().run_in_executor(None, _process_hard_reset)


def _process_hard_reset():
    """Wipe state, copy everything, translate all .tex files."""
    logger.info("Starting hard reset — re-translating everything from scratch...")
    git = GitService()
    llm = LLMService()
    parser = LatexParser()
    state = {"last_sha": None, "files": {}}

    with tempfile.TemporaryDirectory() as temp_dir:
        src_dir = os.path.join(temp_dir, "src")
        target_dir = os.path.join(temp_dir, "target")
        try:
            git.clone_src(src_dir)
            git.clone_target(target_dir)

            all_files_output = git._run_command(["git", "ls-files"], cwd=src_dir)
            changed_files = set(all_files_output.splitlines())

            state = _apply_delta(
                git, llm, parser,
                src_dir, target_dir,
                changed_files=changed_files,
                removed_files=set(),
                state=state,
                commit_msg="GitTranslate: hard reset — full re-translation",
            )

            head_sha = git._run_command(
                ["git", "rev-parse", "HEAD"], cwd=src_dir
            ).strip()
            state["last_sha"] = head_sha
            _save_state(state)
            logger.info("Hard reset completed successfully.")
        except Exception as e:
            logger.error(f"Hard reset failed: {e}")


@app.post("/translate", summary="Translate specific file paths on demand")
async def translate_paths(req: TranslateRequest, background_tasks: BackgroundTasks):
    """
    Clone both repos, translate only the requested `.tex` files, and push.

    - `use_ignore=false` (default): `.gittranslate-ignore` is bypassed — all paths are translated.
    - `use_ignore=true`: paths matching `.gittranslate-ignore` patterns are silently skipped.
    - Non-`.tex` paths are copied unchanged (no translation attempted).
    - Returns 409 if a sync is already in progress.
    """
    if _sync_lock.locked():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    background_tasks.add_task(_translate_specific, req.paths, req.use_ignore)
    return {"status": "accepted", "paths": req.paths}
