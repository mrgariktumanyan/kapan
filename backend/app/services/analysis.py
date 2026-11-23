"""Запуск сверки по камере: выбор входных версий, проверка совместимости, расчёт, сохранение."""
from __future__ import annotations

import logging
import traceback

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core import ENGINE_VERSION
from ..core.reconciliation import ReconciliationInput, ReconciliationParams, run_reconciliation
from ..models import (AnalysisJob, AuditLog, DilutionResult, JobStatus, ModelRole, OreLossResult,
                      Stope, UploadedFile, ValidationStatus, utcnow)
from ..validation.checks import check_compatibility
from .models_io import load_stored

log = logging.getLogger(__name__)

REQUIRED_ROLES = (ModelRole.stope_design, ModelRole.orebody, ModelRole.survey_solid)
OPTIONAL_ROLES = (ModelRole.low_grade, ModelRole.block_model)
ROLE_LABELS = {
    ModelRole.stope_design: "проектный солид камеры",
    ModelRole.orebody: "солид рудного тела",
    ModelRole.survey_solid: "солид фактической съёмки",
}


class AnalysisNotReady(ValueError):
    pass


def select_inputs(db: Session, stope: Stope, file_ids: dict[str, int] | None = None) -> dict[ModelRole, UploadedFile]:
    """По умолчанию — последние активные версии каждой роли; можно явно указать файлы."""
    chosen: dict[ModelRole, UploadedFile] = {}
    file_ids = file_ids or {}
    for role in REQUIRED_ROLES + OPTIONAL_ROLES:
        rec = None
        if role.value in file_ids:
            rec = db.get(UploadedFile, file_ids[role.value])
            if rec is None or rec.stope_id != stope.id or rec.model_role != role:
                raise AnalysisNotReady(f"Файл {file_ids[role.value]} не относится к роли {role.value} этой камеры")
        else:
            rec = db.scalars(
                select(UploadedFile).where(UploadedFile.stope_id == stope.id, UploadedFile.model_role == role,
                                           UploadedFile.is_active.is_(True))
                .order_by(UploadedFile.version.desc())
            ).first()
        if rec is not None:
            if rec.validation_status == ValidationStatus.error:
                raise AnalysisNotReady(f"Файл «{rec.original_name}» не прошёл проверку — расчёт не запускается")
            chosen[role] = rec
    missing = [ROLE_LABELS[r] for r in REQUIRED_ROLES if r not in chosen]
    if missing:
        raise AnalysisNotReady("Не загружены обязательные модели: " + ", ".join(missing))
    bboxes = {r.value: f.summary.get("bbox") for r, f in chosen.items()}
    compat = check_compatibility(bboxes)
    if compat.errors:
        raise AnalysisNotReady("; ".join(c["message"] for c in compat.errors))
    return chosen


def create_job(db: Session, stope: Stope, user_id: int | None, params: dict,
               file_ids: dict[str, int] | None = None) -> AnalysisJob:
    chosen = select_inputs(db, stope, file_ids)
    ReconciliationParams(**params)  # валидация параметров до постановки в очередь
    last = db.scalars(select(AnalysisJob.version).where(AnalysisJob.stope_id == stope.id)
                      .order_by(AnalysisJob.version.desc())).first() or 0
    job = AnalysisJob(
        stope_id=stope.id, version=last + 1, status=JobStatus.queued, params=params,
        engine_version=ENGINE_VERSION, created_by_id=user_id,
        inputs={r.value: {"file_id": f.id, "sha256": f.sha256, "name": f.original_name, "version": f.version}
                for r, f in chosen.items()},
    )
    db.add(job)
    db.add(AuditLog(user_id=user_id, action="analysis.create", entity="stope", entity_id=stope.id,
                    details={"version": job.version, "inputs": job.inputs}))
    db.commit()
    db.refresh(job)
    return job


def _progress(db: Session, job: AnalysisJob, p: float, msg: str):
    job.progress, job.message = p, msg
    db.commit()


def execute_job(db: Session, job_id: int) -> None:
    job = db.get(AnalysisJob, job_id)
    if job is None:
        return
    try:
        job.status = JobStatus.running
        _progress(db, job, 0.05, "Чтение и проверка исходных моделей")
        loaded = {}
        for role, info in job.inputs.items():
            rec = db.get(UploadedFile, info["file_id"])
            lm = load_stored(rec)
            if not lm.usable:
                raise AnalysisNotReady("; ".join(c["message"] for c in lm.report.errors))
            loaded[ModelRole(role)] = lm
        _progress(db, job, 0.3, "Булевы операции и расчёт показателей")
        params = ReconciliationParams(**job.params)
        result = run_reconciliation(ReconciliationInput(
            design=loaded[ModelRole.stope_design].mesh,
            orebody=loaded[ModelRole.orebody].mesh,
            survey=loaded[ModelRole.survey_solid].mesh,
            low_grade=loaded[ModelRole.low_grade].mesh if ModelRole.low_grade in loaded else None,
            block_model=loaded[ModelRole.block_model].block_model if ModelRole.block_model in loaded else None,
            params=params,
        ))
        result["inputs"] = job.inputs
        result["input_quality"] = {r.value: lm.report.status for r, lm in loaded.items()}
        _progress(db, job, 0.9, "Сохранение результатов")
        ol, dl = result["ore_loss"], result["dilution"]
        job.ore_loss = OreLossResult(
            v_plan_ore=ol["V_plan_ore"], v_extracted_ore=ol["V_extracted_ore"], v_loss=ol["V_loss"],
            loss_pct=ol["ore_loss_pct"], t_plan_ore=ol["T_plan_ore"], t_loss=ol["T_loss"],
            metal_loss=ol["metal_loss"])
        job.dilution = DilutionResult(
            v_actual=dl["V_actual"], v_ore=dl["V_ore"], v_low_grade=dl["V_low_grade"], v_waste=dl["V_waste"],
            v_undefined=dl["V_undefined"], dilution_volume_pct=dl["dilution_volume_pct"],
            dilution_tonnage_pct=dl["dilution_tonnage_pct"], planned_dilution_pct=dl["planned_dilution_pct"],
            unplanned_dilution_pct=dl["unplanned_dilution_pct"], t_ore=dl["T_ore"], t_waste=dl["T_waste"])
        job.result = result
        job.status = JobStatus.done
        job.progress, job.message = 1.0, "Готово"
        job.finished_at = utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 — любая ошибка фиксируется в задаче
        db.rollback()
        job = db.get(AnalysisJob, job_id)
        job.status = JobStatus.failed
        job.message = str(exc) if isinstance(exc, (AnalysisNotReady, ValueError)) else f"Внутренняя ошибка: {exc}"
        job.finished_at = utcnow()
        db.commit()
        log.error("Analysis job %s failed: %s", job_id, traceback.format_exc())
