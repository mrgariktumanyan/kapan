from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditLog, Role, User
from ..schemas import Token, UserCreate, UserOut
from ..security import create_token, get_current_user, hash_password, require_roles, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/auth/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalars(select(User).where(User.username == form.username)).first()
    if user is None or not user.is_active or not verify_password(form.password, user.password_hash):
        db.add(AuditLog(action="auth.login_failed", entity="user", details={"username": form.username}))
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный логин или пароль")
    db.add(AuditLog(user_id=user.id, action="auth.login", entity="user", entity_id=user.id))
    db.commit()
    return Token(access_token=create_token(user))


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), _: User = Depends(require_roles(Role.admin))):
    return db.scalars(select(User).order_by(User.username)).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), admin: User = Depends(require_roles(Role.admin))):
    if db.scalars(select(User).where(User.username == body.username)).first():
        raise HTTPException(409, "Пользователь с таким логином уже существует")
    user = User(username=body.username, full_name=body.full_name, role=body.role,
                password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    db.add(AuditLog(user_id=admin.id, action="user.create", entity="user", entity_id=user.id,
                    details={"username": user.username, "role": user.role.value}))
    db.commit()
    return user
