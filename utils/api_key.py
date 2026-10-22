"""API Key 產生與雜湊。資料庫只存 SHA-256 雜湊與前後幾碼，完整金鑰只在建立時回傳一次。"""
import hashlib
import secrets
import string

API_KEY_PREFIX = "sk-lp-"
_ALPHABET = string.ascii_letters + string.digits
_BODY_LEN = 40


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str, str]:
    """回傳 (完整金鑰, 顯示前綴, 末四碼, sha256 雜湊)。"""
    body = "".join(secrets.choice(_ALPHABET) for _ in range(_BODY_LEN))
    full_key = f"{API_KEY_PREFIX}{body}"
    return full_key, full_key[:len(API_KEY_PREFIX) + 4], full_key[-4:], hash_api_key(full_key)
