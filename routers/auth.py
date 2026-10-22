from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.users import User
from schemas.admin import PasswordChange, ProfileUpdate
from services import audit, system_settings
from services.accounts import me_out
from utils.auth import (LOCK_AFTER_FAILURES, LOCK_MINUTES, create_access_token, get_current_user, hash_password,
                        validate_password_strength, verify_password)
from utils.db_conn import get_db

router = APIRouter(prefix="/api", tags=["登入與自己的帳號"])


@router.post("/auth/login", summary="登入（username 填 Email）")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = (form.username or "").strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    guard = system_settings.get_all(db)["login_guard"]
    now = datetime.now()
    if user and guard and user.locked_until and user.locked_until > now:
        minutes = max(1, int((user.locked_until - now).total_seconds() // 60) + 1)
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=f"登入失敗太多次，請 {minutes} 分鐘後再試")
    if user is None or not verify_password(form.password, user.hashed_password):
        if user and guard:
            user.failed_logins += 1
            if user.failed_logins >= LOCK_AFTER_FAILURES:
                user.failed_logins, user.locked_until = 0, now + timedelta(minutes=LOCK_MINUTES)
            db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email 或密碼不正確")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="帳號已停用，請找管理者")
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    db.commit()
    return {"access_token": create_access_token(user.id), "token_type": "bearer", "user": me_out(user)}


@router.get("/auth/me", summary="目前登入的帳號")
def me(user: User = Depends(get_current_user)):
    return me_out(user)


@router.post("/auth/password", summary="變更自己的密碼")
def change_password(body: PasswordChange, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="目前密碼不正確")
    if body.new_password == body.current_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="新密碼不能跟目前的一樣")
    validate_password_strength(body.new_password)
    user.hashed_password = hash_password(body.new_password)
    user.must_change_password = False
    audit.record(db, user, "變更密碼", user.email, commit=False)
    db.commit()
    return me_out(user)


@router.patch("/me", summary="修改自己的顯示名稱")
def update_profile(body: ProfileUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user.name = body.name.strip()
    db.commit()
    return me_out(user)
