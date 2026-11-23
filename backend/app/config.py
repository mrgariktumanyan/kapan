"""Настройки приложения (переменные окружения с префиксом KAPAN_)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("KAPAN_DATABASE_URL", "sqlite:///./kapan.db")
    storage_dir: Path = Path(os.getenv("KAPAN_STORAGE_DIR", "./storage"))
    secret_key: str = os.getenv("KAPAN_SECRET_KEY", "change-me-in-production")
    token_ttl_minutes: int = int(os.getenv("KAPAN_TOKEN_TTL_MINUTES", "720"))
    admin_username: str = os.getenv("KAPAN_ADMIN_USERNAME", "admin")
    admin_password: str | None = os.getenv("KAPAN_ADMIN_PASSWORD")
    max_upload_mb: int = int(os.getenv("KAPAN_MAX_UPLOAD_MB", "1024"))
    cors_origins: tuple[str, ...] = tuple(
        o.strip() for o in os.getenv("KAPAN_CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()
    )
    # Выполнять анализ синхронно (для тестов) или фоновой задачей
    run_jobs_inline: bool = os.getenv("KAPAN_RUN_JOBS_INLINE", "0") == "1"


settings = Settings()
