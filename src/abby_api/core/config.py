from __future__ import annotations

from functools import lru_cache
from typing import Literal

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
    worker_backend: Literal["in_process", "inline", "celery_stub"] = Field(
        default="in_process",
        alias="ABBY_WORKER_BACKEND",
    )
    worker_threads: int = Field(default=1, ge=1, alias="ABBY_WORKER_THREADS")
    # Phase 5: dedicated simulation worker profile.
    # Uses the same backend types as the general worker but is isolated so that
    # long-running GROMACS jobs don't block the default prediction queue.
    simulation_worker_backend: Literal["in_process", "inline", "celery_stub"] = Field(
        default="in_process",
        alias="ABBY_SIMULATION_WORKER_BACKEND",
    )
    simulation_worker_threads: int = Field(default=1, ge=1, alias="ABBY_SIMULATION_WORKER_THREADS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def api_key_set(self) -> set[str]:
        return {item.strip() for item in self.api_keys.split(",") if item.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
