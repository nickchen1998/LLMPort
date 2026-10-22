"""用量統計與請求紀錄（管理者看全部會員）。"""
import csv
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.llm_models import LLMModel
from models.users import User
from services import usage
from utils.auth import require_admin
from utils.db_conn import get_db

router = APIRouter(prefix="/api", tags=["用量統計"])


@router.get("/usage", summary="每日用量（依模型）與依會員彙總")
def usage_report(days: int = Query(14, ge=1, le=90), user_id: int | None = None, model_id: int | None = None,
                 admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    series = usage.daily_series(db, days, user_id=user_id, model_id=model_id)
    per_user = usage.by_user(db, days, model_id=model_id)
    month = usage.month_used_all(db)
    users = {u.id: u for u in db.query(User).filter(User.id.in_(per_user.keys() or [0])).all()}
    rows = [{"user_id": uid, "name": users[uid].name if uid in users else "（已刪除）",
             "is_admin": bool(uid in users and users[uid].is_admin), "is_active": bool(uid in users and users[uid].is_active),
             "monthly_token_quota": users[uid].monthly_token_quota if uid in users else 0,
             "month_used": month.get(uid, 0), **r}
            for uid, r in per_user.items() if not user_id or uid == user_id]
    return {**series, "by_user": sorted(rows, key=lambda r: -(r["prompt_tokens"] + r["completion_tokens"]))}


@router.get("/usage/export.csv", summary="匯出每日用量 CSV")
def export_csv(days: int = Query(30, ge=1, le=366), admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    from models.usage import UsageDaily

    start = usage.day_range(days)[0]
    users = {u.id: u for u in db.query(User).all()}
    models = {m.id: m for m in db.query(LLMModel).all()}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["date", "member", "email", "api_key_id", "model", "requests", "errors", "prompt_tokens", "completion_tokens"])
    for r in db.query(UsageDaily).filter(UsageDaily.date >= start).order_by(UsageDaily.date, UsageDaily.user_id).all():
        user, model = users.get(r.user_id), models.get(r.model_id)
        writer.writerow([r.date.isoformat(), user.name if user else "", user.email if user else "", r.api_key_id,
                         model.api_name if model else "", r.requests, r.errors, r.prompt_tokens, r.completion_tokens])
    return StreamingResponse(iter(["﻿" + buf.getvalue()]), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": f'attachment; filename="llmport-usage-{days}d.csv"'})


@router.get("/requests", summary="請求紀錄（全部會員）")
def requests(limit: int = Query(100, ge=1, le=500), status_filter: str | None = Query(None, alias="status"),
             user_id: int | None = None, model_id: int | None = None, endpoint: str | None = None,
             admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return usage.request_rows(db, limit=limit, user_id=user_id, model_id=model_id, endpoint=endpoint, status=status_filter)
