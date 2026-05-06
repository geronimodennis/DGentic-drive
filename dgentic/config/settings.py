"""Configuration management for DGentic platform."""
import os
from typing import Optional
from enum import Enum
from pydantic_settings import BaseSettings


class PermissionMode(str, Enum):
    """Permission modes for action execution."""
    AUTOPILOT = "autopilot"
    APPROVAL_REQUIRED = "approval_required"


class Environment(str, Enum):
    """Application environments."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    """Application settings."""
    # Environment
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_title: str = "DGentic API"
    api_version: str = "0.1.0"
    
    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/dgentic"
    redis_url: str = "redis://localhost:6379"
    
    # External APIs
    openai_api_key: Optional[str] = None
    google_ai_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    
    # Security
    permission_mode: PermissionMode = PermissionMode.APPROVAL_REQUIRED
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Storage & Paths
    root_directory: str = os.path.expanduser("~/dgentic_workspace")
    localmcp_directory: str = "localmcp"
    memory_directory: str = "memory"
    logs_directory: str = "logs"
    
    # Memory & Vector DB
    vector_db_type: str = "faiss"  # faiss or qdrant
    vector_db_dimension: int = 1536  # OpenAI embeddings default
    vector_db_path: str = "faiss_index"
    
    # Agent Configuration
    max_concurrent_agents: int = 10
    agent_timeout_seconds: int = 300
    
    # Tool Runtime
    tool_timeout_seconds: int = 60
    tool_max_memory_mb: int = 512
    enable_docker_sandbox: bool = False
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # json or text
    
    # Feature Flags
    enable_web_search: bool = True
    enable_code_execution: bool = True
    enable_file_operations: bool = True
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        case_sensitive = False


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()
