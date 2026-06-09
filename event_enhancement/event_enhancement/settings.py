"""Runtime settings from environment."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    expansion_config_path: Path = Field(
        default=Path("config/expansion.yaml"),
        alias="EXPANSION_CONFIG_PATH",
    )
    embedding_model_id: str = Field(default="BAAI/bge-m3", alias="EMBEDDING_MODEL_ID")
    gdelt_base_url: str = Field(
        default="https://api.gdeltproject.org/api/v2/doc/doc",
        alias="GDELT_BASE_URL",
    )

    def expansion_config_absolute(self) -> Path:
        p = self.expansion_config_path
        if p.is_absolute():
            return p
        # relative to cwd (event_enhancement project root)
        return Path.cwd() / p
