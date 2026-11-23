"""Проекты, рудники, горизонты, камеры (ТЗ: Project Management)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AnalysisJob, AuditLog, JobStatus, Level, Mine, Project, Role, Stope, User
from ..schemas import (LevelCreate, LevelOut, MineCreate, MineOut, ProjectCreate, ProjectOut, ProjectUpdate,
                       StopeCreate, StopeOut, StopeTreeItem, StopeUpdate)
from ..security import get_current_user, require_roles

router = APIRouter(prefix="/api", tags=["projects"])
editor = require_roles(Role.planner)


def _get(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__name__} {id_} не найден")
    return obj


def _commit(db: Session, what: str):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"{what} с таким именем уже существует") from None


def _audit(db: Session, user: User, action: str, entity: str, entity_id: int | None, **details):
    db.add(AuditLog(user_id=user.id, action=action, entity=entity, entity_id=entity_id, details=details))


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Project).order_by(Project.name)).all()


@router.post("/projects", response_model=ProjectOut, status_code=201)
def create_project(body: ProjectCreate, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = Project(**body.model_dump())
    db.add(p)
    _commit(db, "Проект")
    _audit(db, user, "project.create", "project", p.id, name=p.name)
    db.commit()
    return p


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _get(db, Project, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    p = _get(db, Project, project_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p, k, v)
    _audit(db, user, "project.update", "project", p.id, changes=changes)
    _commit(db, "Проект")
    return p


@router.get("/projects/{project_id}/mines", response_model=list[MineOut])
def list_mines(project_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Mine).where(Mine.project_id == project_id).order_by(Mine.name)).all()


@router.post("/projects/{project_id}/mines", response_model=MineOut, status_code=201)
def create_mine(project_id: int, body: MineCreate, db: Session = Depends(get_db), user: User = Depends(editor)):
    _get(db, Project, project_id)
    m = Mine(project_id=project_id, name=body.name)
    db.add(m)
    _commit(db, "Рудник")
    _audit(db, user, "mine.create", "mine", m.id, name=m.name)
    db.commit()
    return m


@router.get("/mines/{mine_id}/levels", response_model=list[LevelOut])
def list_levels(mine_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Level).where(Level.mine_id == mine_id).order_by(Level.name)).all()


@router.post("/mines/{mine_id}/levels", response_model=LevelOut, status_code=201)
def create_level(mine_id: int, body: LevelCreate, db: Session = Depends(get_db), user: User = Depends(editor)):
    _get(db, Mine, mine_id)
    lv = Level(mine_id=mine_id, **body.model_dump())
    db.add(lv)
    _commit(db, "Горизонт")
    _audit(db, user, "level.create", "level", lv.id, name=lv.name)
    db.commit()
    return lv


@router.post("/levels/{level_id}/stopes", response_model=StopeOut, status_code=201)
def create_stope(level_id: int, body: StopeCreate, db: Session = Depends(get_db), user: User = Depends(editor)):
    _get(db, Level, level_id)
    s = Stope(level_id=level_id, **body.model_dump())
    db.add(s)
    _commit(db, "Камера")
    _audit(db, user, "stope.create", "stope", s.id, name=s.name)
    db.commit()
    return s


@router.get("/stopes/{stope_id}", response_model=StopeTreeItem)
def get_stope(stope_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    s = _get(db, Stope, stope_id)
    return _tree_item(db, s)


@router.patch("/stopes/{stope_id}", response_model=StopeOut)
def update_stope(stope_id: int, body: StopeUpdate, db: Session = Depends(get_db), user: User = Depends(editor)):
    s = _get(db, Stope, stope_id)
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(s, k, v)
    _audit(db, user, "stope.update", "stope", s.id, changes={k: str(v) for k, v in changes.items()})
    _commit(db, "Камера")
    return s


def _tree_item(db: Session, s: Stope) -> StopeTreeItem:
    job = db.scalars(select(AnalysisJob).where(AnalysisJob.stope_id == s.id, AnalysisJob.status == JobStatus.done)
                     .order_by(AnalysisJob.version.desc())).first()
    last = None
    if job is not None:
        last = {"id": job.id, "version": job.version, "finished_at": job.finished_at.isoformat() if job.finished_at else None,
                "ore_loss_pct": job.ore_loss.loss_pct if job.ore_loss else None,
                "dilution_pct": job.dilution.dilution_volume_pct if job.dilution else None}
    return StopeTreeItem(**StopeOut.model_validate(s).model_dump(), level_name=s.level.name,
                         mine_name=s.level.mine.name, last_analysis=last)


@router.get("/projects/{project_id}/stopes", response_model=list[StopeTreeItem])
def list_project_stopes(project_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _get(db, Project, project_id)
    stopes = db.scalars(select(Stope).join(Level).join(Mine).where(Mine.project_id == project_id)
                        .order_by(Mine.name, Level.name, Stope.name)).all()
    return [_tree_item(db, s) for s in stopes]
