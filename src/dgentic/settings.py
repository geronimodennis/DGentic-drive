from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="DGENTIC_",
        extra="ignore",
    )

    app_name: str = "DGentic"
    environment: str = "development"
    root_dir: Path = Field(default=Path("."))
    data_dir: Path = Field(default=Path(".dgentic"))
    database_url: str | None = None
    autopilot_enabled: bool = False
    auth_enabled: bool | None = None
    auth_tokens: str = ""
    approval_digest_key: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    lm_studio_base_url: str = "http://127.0.0.1:1234"

    @property
    def effective_auth_enabled(self) -> bool:
        if self.auth_enabled is not None:
            return self.auth_enabled
        return self.environment.lower() in {"production", "staging"}

    @property
    def effective_database_url(self) -> str:
        if self.database_url:
            return self.database_url

        data_dir = self.data_dir
        if not data_dir.is_absolute():
            data_dir = self.root_dir / data_dir

        database_path = data_dir / "dgentic.db"
        return f"sqlite:///{database_path.as_posix()}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
