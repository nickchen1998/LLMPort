"""管理者管理會員帳號：建立帳號（產生初始密碼）、設上限、重設密碼、撤銷金鑰。每個帳號都能用全部啟用中的模型。

管理者不能替會員建立金鑰，也看不到完整金鑰。
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from models.users import ApiKey, User
from schemas.admin import MemberCreate, MemberUpdate
from services import audit, usage
from services.accounts import clean_email, key_out, member_out, revoke_key
from utils.auth import generate_password, hash_password, require_admin
from utils.db_conn import get_db

router = APIRouter(prefix="/api", tags=["會員管理"])


def _member(db: Session, member_id: int) -> User:
    user = db.get(User, member_id)
    if user is None or user.is_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到這位會員")
    return user


@router.get("/members", summary="會員清單")
def list_members(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    month = usage.month_used_all(db)
    users = (db.query(User).filter(User.is_staff.is_(False), User.is_superuser.is_(False)).order_by(User.id).all())
    return [member_out(u, month.get(u.id, 0)) for u in users]


@router.post("/members", status_code=status.HTTP_201_CREATED, summary="建立會員（初始密碼只回傳這一次）")
def create_member(body: MemberCreate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    password = generate_password()
    user = User(email=clean_email(db, body.email), name=body.name.strip(), note=body.note,
                hashed_password=hash_password(password), must_change_password=True,
                monthly_token_quota=body.monthly_token_quota, max_keys=body.max_keys)
    db.add(user)
    db.flush()
    audit.record(db, admin, "新增會員", user.name, commit=False)
    db.commit()
    return {"member": member_out(user), "initial_password": password}


@router.get("/members/{member_id}", summary="會員詳情")
def get_member(member_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _member(db, member_id)
    return member_out(user, usage.month_used(db, user.id))


@router.patch("/members/{member_id}", summary="修改會員資料與上限")
def update_member(member_id: int, body: MemberUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _member(db, member_id)
    data = body.model_dump(exclude_unset=True)
    if "email" in data:
        user.email = clean_email(db, data.pop("email"), exclude_id=user.id)
    for field, value in data.items():
        setattr(user, field, value.strip() if field == "name" else value)
    audit.record(db, admin, "修改會員", user.name, detail=body.model_dump(exclude_unset=True), commit=False)
    db.commit()
    return member_out(user, usage.month_used(db, user.id))


@router.post("/members/{member_id}/reset-password", summary="重設會員密碼（臨時密碼只回傳這一次）")
def reset_password(member_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _member(db, member_id)
    password = generate_password()
    user.hashed_password, user.must_change_password = hash_password(password), True
    user.failed_logins, user.locked_until = 0, None
    audit.record(db, admin, "重設會員密碼", user.name, commit=False)
    db.commit()
    return {"password": password}


@router.get("/members/{member_id}/keys", summary="會員的 API Keys（不含完整金鑰）")
def member_keys(member_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    user = _member(db, member_id)
    rows = usage.by_key(db, user.id, date.today().replace(day=1))
    return [key_out(k, rows.get(k.id, {}).get("prompt_tokens", 0) + rows.get(k.id, {}).get("completion_tokens", 0))
            for k in user.api_keys]


@router.delete("/keys/{key_id}", summary="撤銷任何會員的 API Key")
def revoke_member_key(key_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    key = db.get(ApiKey, key_id)
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到這把金鑰")
    revoke_key(key, admin)
    audit.record(db, admin, "撤銷 API Key", f"{key.user.name} · {key.name}", commit=False)
    db.commit()
    return key_out(key)


@router.get("/members/{member_id}/usage", summary="會員的用量")
def member_usage(member_id: int, days: int = Query(14, ge=1, le=90), admin: User = Depends(require_admin),
                 db: Session = Depends(get_db)):
    user = _member(db, member_id)
    series = usage.daily_series(db, days, user_id=user.id)
    keys = {k.id: k for k in user.api_keys}
    month = usage.by_key(db, user.id, date.today().replace(day=1))
    by_key = [{"api_key_id": kid, "name": keys[kid].name if kid in keys else "測試台",
               "masked": keys[kid].masked if kid in keys else None, **r} for kid, r in month.items()]
    return {**series, "month_by_key": by_key, "month_used": usage.month_used(db, user.id)}
