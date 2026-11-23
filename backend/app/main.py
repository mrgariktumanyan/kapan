"""Reconciliation Kapan MPC — backend API."""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import analyses, auth, files, projects
from .config import settings
from .core import ENGINE_VERSION
from .db import Base, SessionLocal, engine
from .models import Role, User
from .security import hash_password

log = logging.getLogger("kapan")


def init_db() -> None:
    if settings.secret_key == "change-me-in-production":
        log.warning("KAPAN_SECRET_KEY не задан — используется небезопасный ключ по умолчанию")
    Base.metadata.create_all(engine)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        if db.scalars(select(User)).first() is None:
            password = settings.admin_password or secrets.token_urlsafe(12)
            db.add(User(username=settings.admin_username, full_name="Administrator", role=Role.admin,
                        password_hash=hash_password(password)))
            db.commit()
            if not settings.admin_password:
                log.warning("Создан администратор %s с временным паролем: %s", settings.admin_username, password)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Reconciliation Kapan MPC", version=ENGINE_VERSION, lifespan=lifespan,
                  description="Сверка, потери и разубоживание очистных камер")
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["*"], allow_headers=["*"])
    for r in (auth.router, projects.router, files.router, analyses.router):
        app.include_router(r)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "engine_version": ENGINE_VERSION}

    return app


app = create_app()
