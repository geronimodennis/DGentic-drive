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
    max_filesystem_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    ollama_base_url: str = "http://127.0.0.1:11434"
    lm_studio_base_url: str = "http://127.0.0.1:1234"
    provider_allowed_base_urls: str = ""
    network_domain_policy: str = ""
    provider_retry_max_attempts: int = Field(default=3, ge=1, le=10)
    provider_retry_initial_delay_seconds: float = Field(default=0.2, ge=0.0, le=30.0)
    provider_retry_max_delay_seconds: float = Field(default=2.0, ge=0.0, le=120.0)
    provider_retry_backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    provider_circuit_breaker_failure_threshold: int = Field(default=3, ge=1, le=100)
    provider_circuit_breaker_cooldown_seconds: float = Field(default=30.0, ge=0.0, le=3600.0)
    provider_pricing_catalog: str = ""
    provider_role_routing: str = ""
    external_openai_compatible_base_url: str = ""
    external_openai_compatible_api_key_env: str = ""
    external_openai_compatible_credential_ref: str = ""
    external_openai_compatible_models: str = ""
    credential_process_adapters: str = ""
    credential_process_timeout_seconds: float = Field(default=5.0, ge=0.1, le=60.0)
    credential_process_max_output_bytes: int = Field(default=4096, ge=1, le=65536)

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
