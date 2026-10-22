"""會員、金鑰與後台帳號的共用邏輯，以及給前端的輸出格式。"""
import re
from datetime import date, datetime, time

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.users import ApiKey, User
from utils.api_key import generate_api_key

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def clean_email(db: Session, email: str, exclude_id: int | None = None) -> str:
    value = (email or "").strip().lower()
    if not _EMAIL.match(value):
        raise bad_request("Email 格式不正確")
    q = db.query(User).filter(func.lower(User.email) == value)
    if exclude_id:
        q = q.filter(User.id != exclude_id)
    if q.first():
        raise bad_request("這個 Email 已經有人用了")
    return value


def _iso(value) -> str | None:
    return value.isoformat(timespec="seconds") if isinstance(value, datetime) else value.isoformat() if value else None


def me_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "must_change_password": user.must_change_password}


def key_out(key: ApiKey, month_tokens: int = 0) -> dict:
    return {"id": key.id, "name": key.name, "masked": key.masked,
            "expires_at": key.expires_at.date().isoformat() if key.expires_at else None, "expired": key.is_expired(),
            "last_used_at": _iso(key.last_used_at), "created_at": _iso(key.created_at),
            "revoked_at": _iso(key.revoked_at), "month_tokens": month_tokens}


def member_out(user: User, month_used: int = 0) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "note": user.note, "is_active": user.is_active,
            "monthly_token_quota": user.monthly_token_quota, "max_keys": user.max_keys,
            "last_login_at": _iso(user.last_login_at), "created_at": _iso(user.created_at), "month_used": month_used,
            "active_keys": sum(1 for k in user.api_keys if not k.is_revoked)}


def admin_out(user: User) -> dict:
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role, "is_active": user.is_active,
            "last_login_at": _iso(user.last_login_at), "created_at": _iso(user.created_at)}


def create_key(db: Session, user: User, name: str,
               expires_on: date | None) -> tuple[ApiKey, str]:
    """建立自己的金鑰（會員不能超過管理者給的上限）。回傳（金鑰, 完整金鑰）。"""
    if not (name or "").strip():
        raise bad_request("請填金鑰名稱")
    active = [k for k in user.api_keys if not k.is_revoked]
    if len(active) >= user.max_keys:
        raise bad_request(f"最多 {user.max_keys} 把有效金鑰，請先撤銷不用的，或請管理者調高上限")
    if expires_on and expires_on <= date.today():
        raise bad_request("到期日要在今天之後")
    full, prefix, last4, hashed = generate_api_key()
    key = ApiKey(user_id=user.id, name=name.strip()[:100], key_prefix=prefix, key_last4=last4, hashed_key=hashed,
                 expires_at=datetime.combine(expires_on, time(23, 59, 59)) if expires_on else None)
    db.add(key)
    db.flush()
    return key, full


def revoke_key(key: ApiKey, by: User) -> None:
    if key.is_revoked:
        raise bad_request("這把金鑰已經撤銷了")
    key.revoked_at = datetime.now()
    key.revoked_by = by.id
