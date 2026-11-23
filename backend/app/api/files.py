"""Data Import Center: загрузка, проверка и версии исходных моделей (ТЗ п. 4)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..importers.formats import SUPPORTED_FORMATS
from ..models import (AuditLog, FileCategory, ModelRole, ProductionRecord, Stope, UploadedFile, User,
                      ValidationStatus)
from ..schemas import FileOut
from ..security import can_upload, get_current_user
from ..services.models_io import load_and_validate, store_file

router = APIRouter(prefix="/api", tags=["files"])

ROLES_BY_CATEGORY: dict[FileCategory, set[ModelRole]] = {
    FileCategory.geological: {ModelRole.orebody, ModelRole.low_grade, ModelRole.block_model, ModelRole.other},
    FileCategory.design: {ModelRole.stope_design, ModelRole.other},
    FileCategory.survey: {ModelRole.survey_solid, ModelRole.survey_points, ModelRole.other},
    FileCategory.production: {ModelRole.production},
}


@router.get("/import/formats")
def formats(_: User = Depends(get_current_user)):
    return {"formats": sorted(SUPPORTED_FORMATS),
            "roles": {c.value: sorted(r.value for r in rs) for c, rs in ROLES_BY_CATEGORY.items()}}


@router.post("/stopes/{stope_id}/files", response_model=FileOut, status_code=201)
async def upload_file(
    stope_id: int,
    category: FileCategory = Form(...),
    model_role: ModelRole = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stope = db.get(Stope, stope_id)
    if stope is None:
        raise HTTPException(404, "Камера не найдена")
    if not can_upload(user, category):
        raise HTTPException(403, f"Роль {user.role.value} не может загружать данные категории {category.value}")
    if model_role not in ROLES_BY_CATEGORY[category]:
        raise HTTPException(422, f"Роль модели {model_role.value} не относится к категории {category.value}")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"Файл больше {settings.max_upload_mb} МБ")
    if not data:
        raise HTTPException(422, "Пустой файл")

    loaded = load_and_validate(data, file.filename or "upload", model_role)
    path, digest = store_file(stope_id, data, file.filename or "upload")

    last = db.scalars(select(UploadedFile.version).where(UploadedFile.stope_id == stope_id,
                                                         UploadedFile.model_role == model_role)
                      .order_by(UploadedFile.version.desc())).first() or 0
    status = ValidationStatus(loaded.report.status)
    if status != ValidationStatus.error and model_role != ModelRole.other:
        # Новая корректная версия становится активной; старые версии сохраняются (ТЗ п. 13)
        db.execute(update(UploadedFile).where(UploadedFile.stope_id == stope_id,
                                              UploadedFile.model_role == model_role).values(is_active=False))
    rec = UploadedFile(
        stope_id=stope_id, category=category, model_role=model_role, version=last + 1,
        original_name=file.filename or "upload", file_format=(file.filename or "").rsplit(".", 1)[-1].lower(),
        sha256=digest, size_bytes=len(data), storage_path=str(path), validation_status=status,
        validation_report=loaded.report.checks, summary=loaded.summary,
        is_active=status != ValidationStatus.error, uploaded_by_id=user.id,
    )
    db.add(rec)
    db.flush()
    if model_role == ModelRole.stope_design and loaded.summary.get("bbox"):
        stope.bbox = loaded.summary["bbox"]
    if model_role == ModelRole.production and loaded.table is not None and status != ValidationStatus.error:
        _store_production(db, stope_id, rec.id, loaded.table)
    db.add(AuditLog(user_id=user.id, action="file.upload", entity="stope", entity_id=stope_id,
                    details={"file_id": rec.id, "name": rec.original_name, "role": model_role.value,
                             "version": rec.version, "sha256": digest, "status": status.value}))
    db.commit()
    db.refresh(rec)
    return rec


def _store_production(db: Session, stope_id: int, file_id: int, df):
    import pandas as pd

    tcol = next(c for c in ("TONNES", "TONNAGE", "TONS", "T") if c in df.columns)
    dcol = next((c for c in ("DATE", "ДАТА") if c in df.columns), None)
    grade_cols = [c for c in ("AU", "AG", "CU", "ZN", "PB") if c in df.columns]
    for _, row in df.iterrows():
        d = pd.to_datetime(row[dcol], errors="coerce").date() if dcol and pd.notna(row[dcol]) else None
        db.add(ProductionRecord(stope_id=stope_id, source_file_id=file_id, record_date=d,
                                tonnes=float(row[tcol]),
                                grades={c: float(row[c]) for c in grade_cols if pd.notna(row[c])}))


@router.get("/stopes/{stope_id}/files", response_model=list[FileOut])
def list_files(stope_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(UploadedFile).where(UploadedFile.stope_id == stope_id)
                      .order_by(UploadedFile.model_role, UploadedFile.version.desc())).all()


@router.get("/files/{file_id}", response_model=FileOut)
def get_file(file_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rec = db.get(UploadedFile, file_id)
    if rec is None:
        raise HTTPException(404, "Файл не найден")
    return rec


@router.get("/files/{file_id}/download")
def download_file(file_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rec = db.get(UploadedFile, file_id)
    if rec is None:
        raise HTTPException(404, "Файл не найден")
    return FileResponse(rec.storage_path, filename=rec.original_name)
