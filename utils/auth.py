"""後台登入（JWT HS256、bcrypt，比照 PTCFormosAI）與角色守衛。

/v1 用的 API Key 驗證在 services/gateway.py，錯誤格式要照 OpenAI，所以不放在這裡。
"""
import re
import secrets
import string
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from models.users import User
from utils.db_conn import get_db
from utils.settings import env_int, settings

ALGORITHM = "HS256"
PASSWORD_MIN_LENGTH = 16
PASSWORD_MAX_BYTES = 72
LOCK_AFTER_FAILURES = 5
LOCK_MINUTES = 15

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def password_problems(password: str) -> list[str]:
    """至少 16 碼、不超過 72 位元組、含大小寫、數字與特殊符號（同 PTCFormosAI）。"""
    p = password or ""
    problems = []
    if len(p) < PASSWORD_MIN_LENGTH:
        problems.append(f"至少 {PASSWORD_MIN_LENGTH} 碼")
    if len(p.encode("utf-8")) > PASSWORD_MAX_BYTES:
        problems.append(f"不可超過 {PASSWORD_MAX_BYTES} 位元組")
    if not re.search(r"[A-Z]", p):
        problems.append("需含大寫字母")
    if not re.search(r"[a-z]", p):
        problems.append("需含小寫字母")
    if not re.search(r"\d", p):
        problems.append("需含數字")
    if not re.search(r"[^A-Za-z0-9]", p):
        problems.append("需含特殊符號")
    return problems


def validate_password_strength(password: str) -> None:
    problems = password_problems(password)
    if problems:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="密碼不符合規則：" + "、".join(problems))


def generate_password() -> str:
    """管理者建立或重設帳號時的初始密碼，一定符合密碼規則。"""
    alphabet = string.ascii_letters + string.digits
    while True:
        body = "".join(secrets.choice(alphabet) for _ in range(16))
        pw = body[:8] + secrets.choice("#%+=@") + body[8:] + secrets.choice(string.digits)
        if not password_problems(pw):
            return pw


def hash_password(password: str) -> str:
    rounds = env_int("BCRYPT_ROUNDS", 12)
    return bcrypt.hashpw((password or "").encode("utf-8")[:PASSWORD_MAX_BYTES], bcrypt.gensalt(rounds=rounds)).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw((plain or "").encode("utf-8")[:PASSWORD_MAX_BYTES], (hashed or "").encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes or settings.access_token_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.secret_key, algorithm=ALGORITHM)


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="請重新登入",
                         headers={"WWW-Authenticate": "Bearer"})


def _user_from_token(db: Session, token: str) -> User:
    try:
        payload = jwt.decode(token or "", settings.secret_key, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise _unauthorized()
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise _unauthorized()
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    return _user_from_token(db, token)


def get_user_from_token_param(token: str = Query(..., description="SSE 用的 JWT"), db: Session = Depends(get_db)) -> User:
    """EventSource 無法帶標頭，改由 query string 帶 token（同 PTCFormosAI）。"""
    return _user_from_token(db, token)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理者權限")
    return user


def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要 Superuser 權限")
    return user


def require_member(user: User = Depends(get_current_user)) -> User:
    if user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="這個功能給會員使用；管理者帳號沒有自己的 API Key")
    return user
