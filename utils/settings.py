"""集中讀取環境變數（每次存取時讀取，方便測試以 monkeypatch 調整）。

可以在後台修改的設定（Metal 上限、預設限制、紀錄保留…）放在資料庫的 system_setting，
見 services/system_settings.py；這裡只放部署時決定、改了要重啟的東西。
"""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

_PLACEHOLDER_SECRETS = {"", "change-me", "change-me-in-production"}


def env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return default if value is None or value == "" else value


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except (TypeError, ValueError):
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _persisted_secret(path: Path) -> str:
    """讀取保存在檔案的隨機金鑰，沒有就建立。刪掉這個檔案會讓所有人重新登入。"""
    try:
        value = path.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(48)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(value)
    return value


class Settings:
    @property
    def app_name(self) -> str:
        return env("APP_NAME", "LLMPort")

    @property
    def app_host(self) -> str:
        return env("APP_HOST", "127.0.0.1")

    @property
    def app_port(self) -> int:
        return env_int("APP_PORT", 8080)

    @property
    def app_reload(self) -> bool:
        return env_bool("APP_RELOAD", False)

    @property
    def tmp_dir(self) -> Path:
        return Path(env("TMP_DIR", str(ROOT / "tmp_files")))

    @property
    def secret_key(self) -> str:
        value = env("SECRET_KEY")
        if value and value not in _PLACEHOLDER_SECRETS:
            return value
        return _persisted_secret(self.tmp_dir / ".secret_key")

    @property
    def access_token_expire_minutes(self) -> int:
        return env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 1440)

    @property
    def redis_url(self) -> str:
        return env("REDIS_URL", "redis://127.0.0.1:6380/0")

    @property
    def model_dir(self) -> Path:
        return Path(env("MODEL_DIR", str(ROOT / "model_files"))).expanduser().resolve()

    @property
    def worker_port_base(self) -> int:
        return env_int("WORKER_PORT_BASE", 9100)

    @property
    def worker_load_timeout(self) -> int:
        return env_int("WORKER_LOAD_TIMEOUT", 900)

    @property
    def fake_workers(self) -> bool:
        return env_bool("FAKE_WORKERS", False)

    @property
    def hf_token(self) -> str | None:
        return env("HF_TOKEN")

    @property
    def api_host(self) -> str | None:
        return env("API_HOST")

    @property
    def console_host(self) -> str | None:
        return env("CONSOLE_HOST")

    @property
    def public_api_base(self) -> str:
        host = self.api_host
        return f"https://{host}/v1" if host else f"http://{self.app_host}:{self.app_port}/v1"

    @property
    def cloudflared_metrics_url(self) -> str | None:
        return env("CLOUDFLARED_METRICS_URL")

    @property
    def static_dir(self) -> Path:
        return ROOT / "templates" / "dist"


settings = Settings()
