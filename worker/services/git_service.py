import os
import subprocess
import logging
from urllib.parse import urlparse
from core.config import settings

logger = logging.getLogger(__name__)


class GitService:
    def __init__(self):
        self.base_url = settings.gitea_url
        self.token = settings.gitea_token
        self._setup_git_author()

    def _setup_git_author(self):
        """Setzt die globalen Git-Nutzerdaten für die Commits des Bots."""
        self._run_command(["git", "config", "--global", "user.name", "TexSync Worker"])
        self._run_command(["git", "config", "--global", "user.email", "worker@texsync.local"])
        # Verhindert, dass Git bei Pulls/Merges im Terminal hängen bleibt und auf Input wartet
        self._run_command(["git", "config", "--global", "core.pager", "cat"])

    def _get_auth_url(self, repo_path: str) -> str:
        """Baut die Git-URL mit dem Token als Authentifizierung (OAuth2-Style)."""
        parsed = urlparse(self.base_url)
        # Format: http://oauth2:<token>@gitea:3000/user/repo.git
        auth_url = f"{parsed.scheme}://oauth2:{self.token}@{parsed.netloc}/{repo_path}.git"
        return auth_url

    def _run_command(self, cmd: list[str], cwd: str = None) -> str:
        """
        Führt einen Shell-Befehl aus.
        WICHTIG: Filtert den Token aus den Fehlermeldungen, falls etwas crasht!
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            # Sicherheit: Token im Error-Log maskieren!
            error_msg = e.stderr.replace(self.token, "***MASKED_TOKEN***") if self.token else e.stderr
            logger.error(f"Git Command Failed: {' '.join(cmd)}\nError: {error_msg}")
            raise RuntimeError(f"Git operation failed: {error_msg}")

    def clone_repo(self, repo_path: str, dest_dir: str):
        """Klont ein Repository in einen Zielordner."""
        repo_url = self._get_auth_url(repo_path)
        logger.info(f"Klone Repository {repo_path} nach {dest_dir}...")
        self._run_command(["git", "clone", repo_url, dest_dir])

    def commit_and_push(self, repo_dir: str, commit_message: str):
        """Fügt alle Änderungen hinzu, committet und pusht sie."""
        logger.info(f"Committing changes in {repo_dir}...")

        # 1. Status prüfen (Gibt es überhaupt Änderungen?)
        status = self._run_command(["git", "status", "--porcelain"], cwd=repo_dir)
        if not status:
            logger.info("Keine Änderungen zum Committen gefunden. Überspringe Push.")
            return

        # 2. Dateien hinzufügen (Add)
        self._run_command(["git", "add", "."], cwd=repo_dir)

        # 3. Commit
        self._run_command(["git", "commit", "-m", commit_message], cwd=repo_dir)

        # 4. Push
        logger.info("Pushe Änderungen zu Gitea...")
        self._run_command(["git", "push", "origin", "main"], cwd=repo_dir)
        # HINWEIS: Falls dein Standard-Branch 'master' heißt, ändere 'main' zu 'master'