from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Git: Source repo
    src_git_url: str
    src_git_token: Optional[str] = None
    # Git: Target repo
    target_git_url: str
    target_git_token: Optional[str] = None
    # Git behavior
    git_branch: str = "main"
    git_author_name: str = "GitTranslate Bot"
    git_author_email: str = "bot@gittranslate.local"
    # LLM (Ollama only)
    llm_api_url: str = "http://host.docker.internal:11434"
    llm_model: str
    llm_timeout: int = 120
    # Translation
    source_lang: str = "German"
    target_lang: str = "English"
    # Webhook security
    webhook_secret: Optional[str] = None
    # Sync / polling
    poll_interval: int = 0          # seconds; 0 = manual /sync only
    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
