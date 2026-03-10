from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional


class Settings(BaseSettings):
    # Gitea
    gitea_url: str
    gitea_token: Optional[str] = None
    src_repo_path: str
    target_repo_path: str

    # Ollama (mit sinnvollen Defaults)
    ollama_host: str = "http://host.docker.internal:11434"
    ollama_model: str
    ollama_timeout: int = 120

    # Logging
    log_level: str = "INFO"

    # Pydantic liest automatisch aus der .env Datei
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignoriert .env Variablen, die hier nicht definiert sind (wie DB_PASSWORD)
    )


# Wir instanziieren die Settings genau einmal.
# Diese Variable importieren wir später überall.
settings = Settings()