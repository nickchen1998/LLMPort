"""後台可以修改的系統設定：存在 system_setting，沒有設定過的用預設值。"""
from sqlalchemy.orm import Session

from models.system import SystemSetting
from services import metrics


def default_metal_limit_gb() -> float:
    """macOS 預設讓 GPU 鎖定約 2/3 的實體記憶體（36 GB 以上約 3/4），取到 0.5 GB。"""
    total = metrics.total_memory_gb()
    return round(total * (2 / 3 if total <= 36 else .75) * 2) / 2


def defaults() -> dict:
    return {
        "metal_limit_gb": default_metal_limit_gb(),
        "headroom_gb": 1.0,
        "default_quota_m": 5.0,
        "default_max_keys": 10,
        "retention_days": 90,
        "restore_on_boot": False,
        "login_guard": True,
        "last_loaded": [],          # 系統用：關機前載入的模型 id，restore_on_boot 開啟時使用
    }


EDITABLE = {
    "metal_limit_gb": float,
    "headroom_gb": float,
    "default_quota_m": float,
    "default_max_keys": int,
    "retention_days": int,
    "restore_on_boot": bool,
    "login_guard": bool,
}


def get_all(db: Session) -> dict:
    values = defaults()
    for row in db.query(SystemSetting).all():
        if row.key in values:
            values[row.key] = row.value
    return values


def validate(changes: dict) -> dict:
    """型別轉換與範圍檢查；有問題丟 ValueError（訊息直接給畫面看）。"""
    clean = {}
    total = metrics.total_memory_gb()
    for key, value in changes.items():
        if key not in EDITABLE:
            raise ValueError(f"不能修改 {key}")
        kind = EDITABLE[key]
        try:
            clean[key] = bool(value) if kind is bool else kind(value)
        except (TypeError, ValueError):
            raise ValueError(f"{key} 的格式不正確")
    rules = {
        "metal_limit_gb": (4, max(4, total - 3), f"Metal 上限要在 4 到 {max(4, total - 3):.0f} GB 之間（至少留 3 GB 給 macOS）"),
        "headroom_gb": (0, 8, "安全餘裕要在 0 到 8 GB 之間"),
        "default_quota_m": (0, 100000, "每月 Token 上限不能是負數"),
        "default_max_keys": (1, 50, "金鑰數量上限要在 1 到 50 之間"),
        "retention_days": (7, 3650, "紀錄保留天數要在 7 到 3650 之間"),
    }
    for key, (lo, hi, message) in rules.items():
        if key in clean and not lo <= clean[key] <= hi:
            raise ValueError(message)
    return clean


def save(db: Session, changes: dict, actor_id: int | None = None) -> None:
    for key, value in changes.items():
        row = db.get(SystemSetting, key) or SystemSetting(key=key)
        row.value = value
        row.updated_by = actor_id
        db.add(row)
    db.commit()
