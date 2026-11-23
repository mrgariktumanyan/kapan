"""Запуск сверки и история анализов камеры."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.reconciliation import FORMULAS, ReconciliationParams
from ..db import SessionLocal, get_db
from ..models import AnalysisJob, AuditLog, Role, Stope, User
from ..schemas import AnalysisCreate, AnalysisDetail, AnalysisOut
from ..security import get_current_user, require_roles
from ..services.analysis import AnalysisNotReady, create_job, execute_job

router = APIRouter(prefix="/api", tags=["analysis"])


def _run_in_background(job_id: int):
    db = SessionLocal()
    try:
        execute_job(db, job_id)
    finally:
        db.close()


@router.get("/analysis/methodology")
def methodology(_: User = Depends(get_current_user)):
    return {"formulas": FORMULAS, "default_params": ReconciliationParams().as_dict()}


@router.post("/stopes/{stope_id}/analyses", response_model=AnalysisOut, status_code=202)
def start_analysis(stope_id: int, body: AnalysisCreate, background: BackgroundTasks,
                   db: Session = Depends(get_db), user: User = Depends(require_roles(Role.planner))):
    stope = db.get(Stope, stope_id)
    if stope is None:
        raise HTTPException(404, "Камера не найдена")
    project_defaults = stope.level.mine.project.settings.get("reconciliation", {})
    params = {**project_defaults, **body.params}
    try:
        job = create_job(db, stope, user.id, params, body.file_ids)
    except (AnalysisNotReady, TypeError) as exc:
        raise HTTPException(422, str(exc)) from None
    if settings.run_jobs_inline:
        execute_job(db, job.id)
        db.refresh(job)
    else:
        background.add_task(_run_in_background, job.id)
    return job


@router.get("/stopes/{stope_id}/analyses", response_model=list[AnalysisOut])
def list_analyses(stope_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(AnalysisJob).where(AnalysisJob.stope_id == stope_id)
                      .order_by(AnalysisJob.version.desc())).all()


@router.get("/analyses/{job_id}", response_model=AnalysisDetail)
def get_analysis(job_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    job = db.get(AnalysisJob, job_id)
    if job is None:
        raise HTTPException(404, "Анализ не найден")
    return job


@router.get("/audit")
def audit(limit: int = 200, db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 1000))).all()
    return [{"id": r.id, "user_id": r.user_id, "action": r.action, "entity": r.entity, "entity_id": r.entity_id,
             "details": r.details, "created_at": r.created_at} for r in rows]
