import subprocess
import logging
from urllib.parse import urlparse, urlunparse
from typing import Optional
from core.config import settings

logger = logging.getLogger(__name__)


class GitService:
    def __init__(self):
        self.src_url = settings.src_git_url
        self.src_token = settings.src_git_token
        self.target_url = settings.target_git_url
        self.target_token = settings.target_git_token
        self.branch = settings.git_branch
        self._setup_git_author()

    def _setup_git_author(self):
        self._run_command(["git", "config", "--global", "user.name", settings.git_author_name])
        self._run_command(["git", "config", "--global", "user.email", settings.git_author_email])
        self._run_command(["git", "config", "--global", "core.pager", "cat"])

    def _build_auth_url(self, full_url: str, token: Optional[str]) -> str:
        """Injects oauth2 token into URL netloc — works for GitHub, GitLab, Gitea."""
        if not token:
            url = full_url if full_url.endswith(".git") else full_url + ".git"
            return url
        parsed = urlparse(full_url)
        netloc = f"oauth2:{token}@{parsed.hostname}"
        if parsed.port:
            netloc += f":{parsed.port}"
        authed = parsed._replace(netloc=netloc)
        url = urlunparse(authed)
        return url if url.endswith(".git") else url + ".git"

    def _run_command(self, cmd: list[str], cwd: str = None) -> str:
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
            error_msg = e.stderr
            # Mask both tokens in error output
            if self.src_token:
                error_msg = error_msg.replace(self.src_token, "***MASKED_TOKEN***")
            if self.target_token:
                error_msg = error_msg.replace(self.target_token, "***MASKED_TOKEN***")
            logger.error(f"Git Command Failed: {' '.join(cmd)}\nError: {error_msg}")
            raise RuntimeError(f"Git operation failed: {error_msg}")

    def clone_src(self, dest_dir: str):
        """Clones the source repository."""
        auth_url = self._build_auth_url(self.src_url, self.src_token)
        logger.info(f"Cloning source repo into {dest_dir}...")
        self._run_command(["git", "clone", "--branch", self.branch, auth_url, dest_dir])

    def clone_target(self, dest_dir: str):
        """Clones the target repository."""
        auth_url = self._build_auth_url(self.target_url, self.target_token)
        logger.info(f"Cloning target repo into {dest_dir}...")
        self._run_command(["git", "clone", "--branch", self.branch, auth_url, dest_dir])

    def get_head_sha(self) -> str:
        """Returns the current HEAD SHA of the source repo without cloning."""
        auth_url = self._build_auth_url(self.src_url, self.src_token)
        output = self._run_command(
            ["git", "ls-remote", auth_url, f"refs/heads/{self.branch}"]
        )
        return output.split("\t")[0]

    def get_diff(self, src_dir: str, old_sha: str, new_sha: str) -> tuple[set, set]:
        """Returns (changed_files, removed_files) between two SHAs."""
        output = self._run_command(
            ["git", "diff", "--name-status", old_sha, new_sha], cwd=src_dir
        )
        changed, removed = set(), set()
        for line in output.splitlines():
            if not line.strip():
                continue
            status, _, path = line.partition("\t")
            if status.startswith("D"):
                removed.add(path.strip())
            else:
                changed.add(path.strip())
        return changed, removed

    def commit_and_push(self, repo_dir: str, commit_message: str):
        """Stages all changes, commits, and pushes to the configured branch."""
        logger.info(f"Committing changes in {repo_dir}...")

        status = self._run_command(["git", "status", "--porcelain"], cwd=repo_dir)
        if not status:
            logger.info("No changes to commit. Skipping push.")
            return

        self._run_command(["git", "add", "."], cwd=repo_dir)
        self._run_command(["git", "commit", "-m", commit_message], cwd=repo_dir)

        logger.info(f"Pushing changes to branch '{self.branch}'...")
        self._run_command(["git", "push", "origin", self.branch], cwd=repo_dir)
