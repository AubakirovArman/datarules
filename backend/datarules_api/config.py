from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "DataRules"
    database_url: str = "postgresql+psycopg://datarules:datarules@127.0.0.1:55433/datarules"
    datarules_secret_key: str = ""
    raw_storage_dir: Path = Path("./storage/raw")
    canonical_storage_dir: Path = Path("./storage/canonical")
    page_image_dir: Path = Path("./storage/page_images")

    gemma_model_id: str = "google/gemma-4-31B-it"
    gemma_base_url: str | None = None
    gemma_api_key: str = "local"
    gemma_gpu_id: int = 2
    gemma_timeout_seconds: int = 180
    enable_gemma_calls: bool = False
    default_db_schema: str = "public"
    embedding_model_id: str = "intfloat/multilingual-e5-large"
    embedding_base_url: str | None = None
    embedding_timeout_seconds: int = 60
    enable_embedding_calls: bool = False
    embedding_dimensions: int = 1024
    keyword_search_engine: str = "pg_search"
    golden_min_score: int = Field(default=75, ge=0, le=100)
    golden_allowed_score_drop: int = Field(default=0, ge=0, le=100)
    golden_fail_on_regression: bool = True
    ingestion_max_attempts: int = Field(default=3, ge=1, le=10)
    ingestion_stale_seconds: int = Field(default=900, ge=30)

    max_upload_mb: int = Field(default=512, ge=1)
    cors_origins: list[str] = [
        "http://localhost:5177",
        "http://127.0.0.1:5177",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.raw_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.canonical_storage_dir.mkdir(parents=True, exist_ok=True)
    settings.page_image_dir.mkdir(parents=True, exist_ok=True)
    return settings
