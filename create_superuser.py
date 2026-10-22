"""
建立第一位 Superuser（之後的後台帳號在後台「後台帳號」頁新增）

互動模式：
    poetry run python create_superuser.py

非互動模式（讀 .env 或參數）：
    SUPERUSER_EMAIL=owner@example.com SUPERUSER_NAME=站長 SUPERUSER_PASSWORD=... poetry run python create_superuser.py
    poetry run python create_superuser.py --email owner@example.com --name 站長 --password ...

Email 已存在時不變更並以 exit code 0 結束；加 --update 會更新密碼並確保是啟用中的 Superuser。
"""
import argparse
import os
import sys
from getpass import getpass

try:
    import readline  # noqa: F401  互動輸入時方向鍵可以編輯
except ImportError:
    pass

from models import import_all_models
from models.users import User
from utils.auth import hash_password, password_problems
from utils.db_conn import get_db_context

import_all_models()


def _resolve(value, env_key):
    value = value or os.getenv(env_key)
    return value.strip() if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description="建立 Superuser")
    parser.add_argument("--email")
    parser.add_argument("--name")
    parser.add_argument("--password")
    parser.add_argument("--update", action="store_true", help="Email 已存在時更新密碼並確保是啟用中的 Superuser")
    args = parser.parse_args()

    email = _resolve(args.email, "SUPERUSER_EMAIL")
    name = _resolve(args.name, "SUPERUSER_NAME") or "站長"
    password = _resolve(args.password, "SUPERUSER_PASSWORD")
    if not (email and password):
        print("=== 建立 Superuser ===")
        while not email:
            email = input("Email: ").strip()
        while not password:
            first = getpass("Password（至少 16 碼，含大小寫、數字與符號）: ")
            if first != getpass("再輸入一次: "):
                print("兩次密碼不一致")
                continue
            password = first
    problems = password_problems(password)
    if problems:
        print("密碼不符合規則：" + "、".join(problems), file=sys.stderr)
        sys.exit(1)

    email = email.lower()
    with get_db_context() as db:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            if not args.update:
                print(f"{email} 已存在，沒有變更（要更新密碼請加 --update）")
                return
            existing.hashed_password = hash_password(password)
            existing.is_superuser = existing.is_staff = existing.is_active = True
            existing.must_change_password = False
            db.commit()
            print(f"Superuser {email} 已更新")
            return
        db.add(User(email=email, name=name, hashed_password=hash_password(password), is_superuser=True, is_staff=True,
                    rpm_limit=600))
        db.commit()
        print(f"Superuser {email} 建立成功")


if __name__ == "__main__":
    main()
