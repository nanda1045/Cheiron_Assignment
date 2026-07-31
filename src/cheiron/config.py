"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings for the Cheiron service."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CHEIRON_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    planner_provider: Literal["auto", "openai", "rules"] = "auto"
    openai_model: str = "gpt-5.6-terra"
    service_name: str = "cheiron"
    api_prefix: str = "/v1"
    clinical_trials_base_url: str = "https://clinicaltrials.gov/api/v2"
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    max_studies: int = Field(default=20_000, ge=1_000, le=100_000)


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide validated settings instance."""

    return Settings()
