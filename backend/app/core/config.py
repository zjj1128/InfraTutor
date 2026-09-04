from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: str = "development"
    database_url: str = "sqlite:///./data/infratutor.db"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    enable_debug_panel: bool = True
    curriculum_dir: Path = Field(default=PROJECT_ROOT / "curriculum")
    llm_mode: Literal["mock", "live"] = "mock"
    llm_provider: Literal["openai"] = "openai"
    llm_assessor_model: str = ""
    llm_teacher_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_timeout_seconds: float = Field(default=30, gt=0, le=600)
    llm_transport_max_retries: int = Field(default=1, ge=0, le=10)
    llm_repair_retries: int = Field(default=1, ge=0, le=1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
