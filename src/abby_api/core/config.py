from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Abby API"
    env: str = Field(default="development", alias="ABBY_ENV")
    api_keys: str = Field(default="dev-local-key", alias="ABBY_API_KEYS")
    model_bundle_version: str = Field(default="2026.07.v1", alias="ABBY_MODEL_BUNDLE_VERSION")
    preprocess_version: str = Field(default="2.1.0", alias="ABBY_PREPROCESS_VERSION")
    database_url: str = Field(
        default="postgresql+psycopg://abby:change-me@localhost:5432/abby",
        alias="ABBY_DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", alias="ABBY_REDIS_URL")
    object_storage_bucket: str = Field(default="abby-dev", alias="ABBY_OBJECT_STORAGE_BUCKET")
    object_storage_endpoint: str = Field(
        default="http://localhost:9000", alias="ABBY_OBJECT_STORAGE_ENDPOINT"
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def api_key_set(self) -> set[str]:
        return {item.strip() for item in self.api_keys.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
