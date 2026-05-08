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
    autopilot_enabled: bool = False
    auth_enabled: bool | None = None
    auth_tokens: str = ""
    ollama_base_url: str = "http://127.0.0.1:11434"
    lm_studio_base_url: str = "http://127.0.0.1:1234"

    @property
    def effective_auth_enabled(self) -> bool:
        if self.auth_enabled is not None:
            return self.auth_enabled
        return self.environment.lower() in {"production", "staging"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
