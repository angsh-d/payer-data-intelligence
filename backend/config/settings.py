"""Application settings loaded from environment variables."""
from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Claude API (Policy Reasoning - NO FALLBACK)
    anthropic_api_key: str = Field(default="", description="Anthropic API key for Claude")

    # Gemini API (Primary for general tasks)
    gemini_api_key: str = Field(default="", description="Google Gemini API key")

    # Azure OpenAI (Fallback for general tasks)
    azure_openai_api_key: str = Field(default="", description="Azure OpenAI API key")
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI endpoint URL")
    azure_openai_deployment: str = Field(default="gpt-4o", description="Azure OpenAI deployment name")
    azure_openai_api_version: str = Field(default="2024-02-15-preview", description="Azure OpenAI API version")

    # Database
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/access_strategy.db",
        description="Database connection URL"
    )
    external_database_url: str = Field(
        default="",
        description="External PostgreSQL database URL (takes priority over database_url)"
    )

    # Application
    app_env: str = Field(default="development", description="Application environment")
    log_level: str = Field(default="INFO", description="Logging level")
    cors_origins: List[str] = Field(
        default=["*"],
        description="Allowed CORS origins"
    )

    # WebSocket
    ws_heartbeat_interval: int = Field(default=30, description="WebSocket heartbeat interval in seconds")

    # Model configurations
    claude_model: str = Field(default="claude-sonnet-4-20250514", description="Claude model for policy reasoning")
    gemini_model: str = Field(default="gemini-3-pro-preview", description="Gemini model for general tasks")

    # Token limits
    gemini_max_output_tokens: int = Field(default=65536, description="Max output tokens for Gemini 2.5")
    claude_max_output_tokens: int = Field(default=8192, description="Max output tokens for Claude")
    azure_max_output_tokens: int = Field(default=4096, description="Max output tokens for Azure OpenAI")

    # Data directories (relative to project root)
    patients_dir: str = Field(default="data/patients", description="Directory containing patient JSON files")
    policies_dir: str = Field(default="data/policies", description="Directory containing policy files")
    historical_data_path: str = Field(default="data/historical_pa_cases.json", description="Path to historical PA cases")


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
