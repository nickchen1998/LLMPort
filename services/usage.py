"""用量：寫入 request_log 與 usage_daily，以及後台圖表、表格要的查詢。"""
from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from models.llm_models import LLMModel
from models.usage import RequestLog, UsageDaily
from models.users import ApiKey, User
from utils.db_conn import get_db_context

LOG_FIELDS = ("request_id", "user_id", "api_key_id", "model_id", "model_name", "endpoint", "status_code", "error_code",
              "prompt_tokens", "completion_tokens", "ttft_ms", "duration_ms", "stream", "has_image", "source",
              "client_country", "user_agent")


def record_request(entry: dict) -> None:
    """同步寫入（從 threadpool 呼叫）。只有知道是哪位會員的請求才進每日彙總。"""
    with get_db_context() as db:
        db.add(RequestLog(**{k: entry.get(k) for k in LOG_FIELDS}))
        if entry.get("user_id"):
            upsert_daily(db, date.today(), entry["user_id"], entry.get("api_key_id") or 0, entry.get("model_id") or 0,
                         ok=entry["status_code"] < 400, prompt=entry.get("prompt_tokens") or 0,
                         completion=entry.get("completion_tokens") or 0)
        if entry.get("api_key_id"):
            key = db.get(ApiKey, entry["api_key_id"])
            now = datetime.now()
            if key and (key.last_used_at is None or now - key.last_used_at > timedelta(seconds=30)):
                key.last_used_at = now
        db.commit()


def upsert_daily(db: Session, day: date, user_id: int, api_key_id: int, model_id: int, *, ok: bool, prompt: int,
                 completion: int) -> None:
    table = UsageDaily.__table__
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    stmt = insert(table).values(date=day, user_id=user_id, api_key_id=api_key_id, model_id=model_id, requests=1,
                                errors=0 if ok else 1, prompt_tokens=prompt, completion_tokens=completion)
    stmt = stmt.on_conflict_do_update(
        index_elements=["date", "user_id", "api_key_id", "model_id"],
        set_={col: table.c[col] + stmt.excluded[col] for col in ("requests", "errors", "prompt_tokens", "completion_tokens")},
    )
    db.execute(stmt)


def prune_logs(retention_days: int) -> int:
    with get_db_context() as db:
        cutoff = datetime.now() - timedelta(days=retention_days)
        count = db.query(RequestLog).filter(RequestLog.created_at < cutoff).delete(synchronize_session=False)
        db.commit()
    return count


# ─── 查詢 ───

def day_range(days: int) -> list[date]:
    today = date.today()
    return [today - timedelta(days=days - 1 - i) for i in range(days)]


def _rows(db: Session, start: date, user_id: int | None = None, model_id: int | None = None,
          api_key_id: int | None = None):
    q = db.query(UsageDaily).filter(UsageDaily.date >= start)
    if user_id:
        q = q.filter(UsageDaily.user_id == user_id)
    if model_id:
        q = q.filter(UsageDaily.model_id == model_id)
    if api_key_id is not None:
        q = q.filter(UsageDaily.api_key_id == api_key_id)
    return q.all()


def daily_series(db: Session, days: int, user_id: int | None = None, model_id: int | None = None) -> dict:
    """每日 token（依模型），給堆疊長條圖。"""
    dates = day_range(days)
    index = {d: i for i, d in enumerate(dates)}
    models = {m.id: m for m in db.query(LLMModel).all()}
    series: dict[int, dict] = {}
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0, "errors": 0}
    for r in _rows(db, dates[0], user_id, model_id):
        s = series.setdefault(r.model_id, {"model_id": r.model_id,
                                           "name": models[r.model_id].api_name if r.model_id in models else "（已刪除的模型）",
                                           "prompt": [0] * days, "completion": [0] * days})
        i = index[r.date]
        s["prompt"][i] += r.prompt_tokens
        s["completion"][i] += r.completion_tokens
        for k in totals:
            totals[k] += getattr(r, k)
    return {"dates": [d.isoformat() for d in dates], "series": sorted(series.values(), key=lambda s: s["model_id"]),
            "totals": totals}


def by_user(db: Session, days: int, model_id: int | None = None) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in _rows(db, day_range(days)[0], model_id=model_id):
        row = out.setdefault(r.user_id, {"requests": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0})
        for k in row:
            row[k] += getattr(r, k)
    return out


def by_key(db: Session, user_id: int, start: date, model_id: int | None = None) -> dict[int, dict]:
    out: dict[int, dict] = {}
    for r in _rows(db, start, user_id=user_id, model_id=model_id):
        row = out.setdefault(r.api_key_id, {"requests": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0})
        for k in row:
            row[k] += getattr(r, k)
    return out


def month_used(db: Session, user_id: int) -> int:
    first = date.today().replace(day=1)
    total = (db.query(func.coalesce(func.sum(UsageDaily.prompt_tokens + UsageDaily.completion_tokens), 0))
             .filter(UsageDaily.user_id == user_id, UsageDaily.date >= first).scalar())
    return int(total or 0)


def month_used_all(db: Session) -> dict[int, int]:
    first = date.today().replace(day=1)
    rows = (db.query(UsageDaily.user_id, func.sum(UsageDaily.prompt_tokens + UsageDaily.completion_tokens))
            .filter(UsageDaily.date >= first).group_by(UsageDaily.user_id).all())
    return {uid: int(total or 0) for uid, total in rows}


def today_totals(db: Session, user_id: int | None = None) -> dict:
    q = db.query(func.coalesce(func.sum(UsageDaily.prompt_tokens), 0), func.coalesce(func.sum(UsageDaily.completion_tokens), 0),
                 func.coalesce(func.sum(UsageDaily.requests), 0), func.coalesce(func.sum(UsageDaily.errors), 0)
                 ).filter(UsageDaily.date == date.today())
    if user_id:
        q = q.filter(UsageDaily.user_id == user_id)
    p, c, r, e = q.one()
    return {"prompt_tokens": int(p), "completion_tokens": int(c), "requests": int(r), "errors": int(e)}


def request_rows(db: Session, *, limit: int = 100, user_id: int | None = None, model_id: int | None = None,
                 endpoint: str | None = None, status: str | None = None, api_key_id: int | None = None) -> list[dict]:
    q = db.query(RequestLog).order_by(RequestLog.id.desc())
    if user_id:
        q = q.filter(RequestLog.user_id == user_id)
    if model_id:
        q = q.filter(RequestLog.model_id == model_id)
    if endpoint:
        q = q.filter(RequestLog.endpoint == endpoint)
    if api_key_id:
        q = q.filter(RequestLog.api_key_id == api_key_id)
    if status == "ok":
        q = q.filter(RequestLog.status_code < 400)
    elif status == "error":
        q = q.filter(RequestLog.status_code >= 400)
    logs = q.limit(min(max(limit, 1), 500)).all()
    users = {u.id: u for u in db.query(User).filter(User.id.in_({r.user_id for r in logs if r.user_id})).all()}
    keys = {k.id: k for k in db.query(ApiKey).filter(ApiKey.id.in_({r.api_key_id for r in logs if r.api_key_id})).all()}
    out = []
    for r in logs:
        user, key = users.get(r.user_id), keys.get(r.api_key_id)
        out.append({
            "id": r.id, "created_at": r.created_at.isoformat(timespec="seconds"), "request_id": r.request_id,
            "user_id": r.user_id, "user_name": user.name if user else None,
            "api_key_id": r.api_key_id, "key_name": key.name if key else ("測試台" if r.source == "playground" else None),
            "key_masked": key.masked if key else None, "model": r.model_name, "model_id": r.model_id,
            "endpoint": r.endpoint, "status_code": r.status_code, "error_code": r.error_code,
            "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens, "ttft_ms": r.ttft_ms,
            "duration_ms": r.duration_ms, "stream": r.stream, "has_image": r.has_image, "source": r.source,
            "client_country": r.client_country,
        })
    return out
