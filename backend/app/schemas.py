from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .models import FileCategory, JobStatus, ModelRole, Role, ValidationStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(ORM):
    id: int
    username: str
    full_name: str
    role: Role
    is_active: bool


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    full_name: str = ""
    password: str = Field(min_length=8)
    role: Role


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    crs: str = "Local mine grid"
    settings: dict = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    crs: str | None = None
    settings: dict | None = None


class ProjectOut(ORM):
    id: int
    name: str
    description: str
    crs: str
    units: str
    settings: dict
    created_at: datetime


class MineCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class MineOut(ORM):
    id: int
    project_id: int
    name: str


class LevelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    elevation: float | None = None


class LevelOut(ORM):
    id: int
    mine_id: int
    name: str
    elevation: float | None


class StopeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    orebody: str = ""
    area: str = ""
    status: str = "planned"
    mined_from: date | None = None
    mined_to: date | None = None
    notes: str = ""


class StopeUpdate(BaseModel):
    name: str | None = None
    orebody: str | None = None
    area: str | None = None
    status: str | None = None
    mined_from: date | None = None
    mined_to: date | None = None
    notes: str | None = None


class StopeOut(ORM):
    id: int
    level_id: int
    name: str
    orebody: str
    area: str
    status: str
    mined_from: date | None
    mined_to: date | None
    notes: str
    bbox: list | None


class StopeTreeItem(StopeOut):
    level_name: str
    mine_name: str
    last_analysis: dict | None = None


class FileOut(ORM):
    id: int
    stope_id: int
    category: FileCategory
    model_role: ModelRole
    version: int
    original_name: str
    file_format: str
    sha256: str
    size_bytes: int
    validation_status: ValidationStatus
    validation_report: list
    summary: dict
    is_active: bool
    uploaded_at: datetime


class AnalysisCreate(BaseModel):
    params: dict = Field(default_factory=dict)
    file_ids: dict[str, int] | None = None


class AnalysisOut(ORM):
    id: int
    stope_id: int
    version: int
    status: JobStatus
    progress: float
    message: str
    params: dict
    inputs: dict
    engine_version: str
    created_at: datetime
    finished_at: datetime | None


class AnalysisDetail(AnalysisOut):
    result: dict | None
