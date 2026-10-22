"""後台帳號（Superuser 與管理員），只有 Superuser 能管。至少要保留一位啟用中的 Superuser。"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from models.audit import AuditLog
from models.users import User
from schemas.admin import AdminCreate, AdminUpdate
from services import audit
from services.accounts import admin_out, bad_request, clean_email
from utils.auth import generate_password, hash_password, require_superuser
from utils.db_conn import get_db

router = APIRouter(prefix="/api", tags=["後台帳號"])


def _admins(db: Session):
    return db.query(User).filter(or_(User.is_staff.is_(True), User.is_superuser.is_(True)))


@router.get("/admins", summary="後台帳號清單")
def list_admins(su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    return [admin_out(u) for u in _admins(db).order_by(User.id).all()]


@router.post("/admins", status_code=status.HTTP_201_CREATED, summary="新增後台帳號（初始密碼只回傳這一次）")
def create_admin(body: AdminCreate, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    password = generate_password()
    user = User(email=clean_email(db, body.email), name=body.name.strip(), hashed_password=hash_password(password),
                is_staff=True, is_superuser=body.is_superuser, must_change_password=True)
    db.add(user)
    db.flush()
    audit.record(db, su, "建立後台帳號", user.email, commit=False)
    db.commit()
    return {"admin": admin_out(user), "initial_password": password}


@router.patch("/admins/{admin_id}", summary="修改後台帳號")
def update_admin(admin_id: int, body: AdminUpdate, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    user = db.get(User, admin_id)
    if user is None or not user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到這個後台帳號")
    losing_su = (body.is_superuser is False or body.is_active is False) and user.is_superuser
    if losing_su:
        others = _admins(db).filter(User.is_superuser.is_(True), User.is_active.is_(True), User.id != user.id).count()
        if not others:
            raise bad_request("至少要保留一位啟用中的 Superuser")
    if body.is_active is False and user.id == su.id:
        raise bad_request("不能停用自己")
    if body.name is not None:
        user.name = body.name.strip()
    if body.is_superuser is not None:
        user.is_superuser = body.is_superuser
        user.is_staff = True
    if body.is_active is not None:
        user.is_active = body.is_active
    audit.record(db, su, "修改後台帳號", user.email, detail=body.model_dump(exclude_unset=True), commit=False)
    db.commit()
    return admin_out(user)


@router.get("/audit", summary="操作紀錄")
def audit_log(limit: int = 200, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(max(limit, 1), 1000)).all()
    return [{"id": r.id, "created_at": r.created_at.isoformat(timespec="seconds"), "actor": r.actor_label,
             "action": r.action, "target": r.target} for r in rows]
