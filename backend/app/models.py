"""Схема базы данных (ТЗ п. 13).

Иерархия: Project → Mine → Level → Stope.
Исходные модели (геология, проект, съёмка, производство) хранятся в UploadedFile
с категорией и ролью; каждая повторная загрузка создаёт новую версию, старые
версии и результаты анализов не удаляются.
"""
from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (JSON, Boolean, Date, DateTime, Enum, Float, ForeignKey, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    admin = "admin"
    planner = "planner"        # Mine Planning Engineer
    surveyor = "surveyor"
    geologist = "geologist"
    management = "management"


class FileCategory(str, enum.Enum):
    geological = "geological"  # A. Geological Model
    design = "design"          # B. Design Model
    survey = "survey"          # C. Survey Model
    production = "production"  # D. Production Data


class ModelRole(str, enum.Enum):
    orebody = "orebody"            # солид кондиционной руды
    low_grade = "low_grade"        # солид некондиционной руды
    block_model = "block_model"    # блочная модель (плотность, содержания)
    stope_design = "stope_design"  # проектный солид камеры
    survey_solid = "survey_solid"  # солид выработанного пространства (CMS)
    survey_points = "survey_points"
    production = "production"      # таблица производственных показателей
    other = "other"


class ValidationStatus(str, enum.Enum):
    ok = "ok"
    warning = "warning"
    error = "error"


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[Role] = mapped_column(Enum(Role, native_enum=False, length=16))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    crs: Mapped[str] = mapped_column(String(128), default="Local mine grid")  # система координат
    units: Mapped[str] = mapped_column(String(8), default="m")
    # Настраиваемые параметры: плотности по умолчанию, допуски, пороги статусов (ТЗ п. 8, 11)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    mines: Mapped[list["Mine"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Mine(Base):
    __tablename__ = "mines"
    __table_args__ = (UniqueConstraint("project_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    project: Mapped[Project] = relationship(back_populates="mines")
    levels: Mapped[list["Level"]] = relationship(back_populates="mine", cascade="all, delete-orphan")


class Level(Base):
    __tablename__ = "levels"
    __table_args__ = (UniqueConstraint("mine_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    mine_id: Mapped[int] = mapped_column(ForeignKey("mines.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))          # напр. «710»
    elevation: Mapped[float | None] = mapped_column(Float, nullable=True)
    mine: Mapped[Mine] = relationship(back_populates="levels")
    stopes: Mapped[list["Stope"]] = relationship(back_populates="level", cascade="all, delete-orphan")


class Stope(Base):
    __tablename__ = "stopes"
    __table_args__ = (UniqueConstraint("level_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    level_id: Mapped[int] = mapped_column(ForeignKey("levels.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))           # напр. «710-SH-025»
    orebody: Mapped[str] = mapped_column(String(128), default="")
    area: Mapped[str] = mapped_column(String(128), default="")  # производственный участок
    status: Mapped[str] = mapped_column(String(32), default="planned")
    mined_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    mined_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    # Габарит проектной камеры (заполняется при загрузке проекта). Пространственный
    # индекс PostGIS будет добавлен на Этапе 2 вместе с 3D-регистрацией.
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    level: Mapped[Level] = relationship(back_populates="stopes")
    files: Mapped[list["UploadedFile"]] = relationship(back_populates="stope", cascade="all, delete-orphan")
    jobs: Mapped[list["AnalysisJob"]] = relationship(back_populates="stope", cascade="all, delete-orphan")


class UploadedFile(Base):
    """Исходный файл модели. Одна запись = одна версия; содержимое неизменно (sha256)."""

    __tablename__ = "uploaded_files"
    id: Mapped[int] = mapped_column(primary_key=True)
    stope_id: Mapped[int] = mapped_column(ForeignKey("stopes.id", ondelete="CASCADE"), index=True)
    category: Mapped[FileCategory] = mapped_column(Enum(FileCategory, native_enum=False, length=16))
    model_role: Mapped[ModelRole] = mapped_column(Enum(ModelRole, native_enum=False, length=16))
    version: Mapped[int] = mapped_column(Integer)           # номер версии в рамках (stope, model_role)
    original_name: Mapped[str] = mapped_column(String(255))
    file_format: Mapped[str] = mapped_column(String(16))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(512))
    validation_status: Mapped[ValidationStatus] = mapped_column(Enum(ValidationStatus, native_enum=False, length=8))
    validation_report: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)  # объём, габарит, число треугольников…
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # последняя версия роли
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stope: Mapped[Stope] = relationship(back_populates="files")


class ProductionRecord(Base):
    __tablename__ = "production_records"
    id: Mapped[int] = mapped_column(primary_key=True)
    stope_id: Mapped[int] = mapped_column(ForeignKey("stopes.id", ondelete="CASCADE"), index=True)
    source_file_id: Mapped[int | None] = mapped_column(ForeignKey("uploaded_files.id"), nullable=True)
    record_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tonnes: Mapped[float] = mapped_column(Float)
    grades: Mapped[dict] = mapped_column(JSON, default=dict)   # {"AU": 3.2, "CU": 0.8}
    metal: Mapped[dict] = mapped_column(JSON, default=dict)


class AnalysisJob(Base):
    """Один запуск сверки. Хранит ссылки и хеши входных файлов, параметры и версию ядра."""

    __tablename__ = "analysis_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    stope_id: Mapped[int] = mapped_column(ForeignKey("stopes.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)           # номер анализа по камере
    status: Mapped[JobStatus] = mapped_column(Enum(JobStatus, native_enum=False, length=8), default=JobStatus.queued)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)  # role -> {file_id, sha256, name, version}
    engine_version: Mapped[str] = mapped_column(String(16), default="")
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # полный результат с формулами
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stope: Mapped[Stope] = relationship(back_populates="jobs")
    ore_loss: Mapped["OreLossResult | None"] = relationship(cascade="all, delete-orphan", uselist=False)
    dilution: Mapped["DilutionResult | None"] = relationship(cascade="all, delete-orphan", uselist=False)


class OreLossResult(Base):
    __tablename__ = "ore_loss_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), unique=True)
    v_plan_ore: Mapped[float] = mapped_column(Float)
    v_extracted_ore: Mapped[float] = mapped_column(Float)
    v_loss: Mapped[float] = mapped_column(Float)
    loss_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    t_plan_ore: Mapped[float] = mapped_column(Float)
    t_loss: Mapped[float] = mapped_column(Float)
    metal_loss: Mapped[dict] = mapped_column(JSON, default=dict)


class DilutionResult(Base):
    __tablename__ = "dilution_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), unique=True)
    v_actual: Mapped[float] = mapped_column(Float)
    v_ore: Mapped[float] = mapped_column(Float)
    v_low_grade: Mapped[float] = mapped_column(Float)
    v_waste: Mapped[float] = mapped_column(Float)
    v_undefined: Mapped[float] = mapped_column(Float)
    dilution_volume_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    dilution_tonnage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    planned_dilution_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    unplanned_dilution_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    t_ore: Mapped[float] = mapped_column(Float)
    t_waste: Mapped[float] = mapped_column(Float)


class PlanActualResult(Base):
    """Этап 3: план-факт с учётом производственных данных."""

    __tablename__ = "plan_actual_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), unique=True)
    rows: Mapped[list] = mapped_column(JSON, default=list)


class AIReport(Base):
    """Этап 5: заключение AI. Хранится отдельно от расчётов и никогда их не изменяет."""

    __tablename__ = "ai_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("analysis_jobs.id", ondelete="CASCADE"), index=True)
    model: Mapped[str] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    references: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
