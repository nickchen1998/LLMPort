"""自己的金鑰、用量與紀錄（所有帳號都有，在服務中心）：一律用登入者的 id 查，不接受從參數指定別人。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from models.users import ApiKey, User
from schemas.admin import KeyCreate
from services import audit, usage
from services.accounts import create_key, key_out, revoke_key
from services.catalog import enabled_models, public_model_out
from services.model_manager import manager
from utils.auth import get_current_user
from utils.db_conn import get_db

router = APIRouter(prefix="/api/me", tags=["自己的金鑰與用量"])


def _month_by_key(db: Session, user: User) -> dict[int, int]:
    rows = usage.by_key(db, user.id, date.today().replace(day=1))
    return {kid: r["prompt_tokens"] + r["completion_tokens"] for kid, r in rows.items()}


@router.get("/summary", summary="我的總覽")
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    month = usage.month_used(db, user.id)
    return {
        "month_used": month, "monthly_token_quota": user.monthly_token_quota,
        "max_keys": user.max_keys, "active_keys": sum(1 for k in user.api_keys if not k.is_revoked),
        "today": usage.today_totals(db, user.id),
        "models": [public_model_out(m, manager.get(m.id).status) for m in enabled_models(db)],
    }


@router.get("/models", summary="我可以使用的模型")
def my_models(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [public_model_out(m, manager.get(m.id).status) for m in enabled_models(db)]


@router.get("/keys", summary="我的 API Keys")
def list_keys(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    month = _month_by_key(db, user)
    return [key_out(k, month.get(k.id, 0)) for k in user.api_keys]


@router.post("/keys", status_code=status.HTTP_201_CREATED, summary="建立 API Key（完整金鑰只回傳這一次）")
def add_key(body: KeyCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key, full = create_key(db, user, body.name, body.expires_on)
    audit.record(db, user, "建立 API Key", f"{user.name} · {key.name}", commit=False)
    db.commit()
    return {**key_out(key), "key": full}


@router.delete("/keys/{key_id}", summary="撤銷自己的 API Key")
def delete_key(key_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.user_id == user.id).first()
    if key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到這把金鑰")
    revoke_key(key, user)
    audit.record(db, user, "撤銷 API Key", f"{user.name} · {key.name}", commit=False)
    db.commit()
    return key_out(key)


@router.get("/usage", summary="我的用量（依模型、依金鑰；帶 api_key_id 只看那一把）")
def my_usage(days: int = Query(14, ge=1, le=90), model_id: int | None = None, api_key_id: int | None = None,
             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    series = usage.daily_series(db, days, user_id=user.id, model_id=model_id, api_key_id=api_key_id)
    start = usage.day_range(days)[0]
    keys = {k.id: k for k in user.api_keys}
    rows = []
    for kid, r in usage.by_key(db, user.id, start, model_id).items():
        key = keys.get(kid)
        rows.append({"api_key_id": kid, "name": key.name if key else "測試台", "masked": key.masked if key else None,
                     "revoked": bool(key and key.is_revoked), **r})
    return {**series, "by_key": sorted(rows, key=lambda r: -(r["prompt_tokens"] + r["completion_tokens"]))}


@router.get("/requests", summary="我的請求紀錄")
def my_requests(limit: int = Query(100, ge=1, le=500), status_filter: str | None = Query(None, alias="status"),
                api_key_id: int | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return usage.request_rows(db, limit=limit, user_id=user.id, status=status_filter, api_key_id=api_key_id)
