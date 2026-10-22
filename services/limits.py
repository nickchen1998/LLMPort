"""限流與本月用量：Redis 計數。Redis 掛掉時放行並記警告（best-effort，同 PTCFormosAI）。"""
import logging
import time
from datetime import date

from sqlalchemy import func
from starlette.concurrency import run_in_threadpool

from models.usage import UsageDaily
from utils.db_conn import get_db_context
from utils.openai_errors import OpenAIError
from utils.redis_conn import get_redis

logger = logging.getLogger(__name__)
QUOTA_TTL = 40 * 86400


async def check_rate(bucket: str, limit: int) -> dict:
    """每分鐘固定視窗；回傳要放進回應的 x-ratelimit-* 標頭（跟 OpenAI 同名）。"""
    now = time.time()
    reset = 60 - int(now % 60)
    key = f"rl:{bucket}:{int(now // 60)}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 70)
    except Exception:  # noqa: BLE001
        logger.warning("限流檢查略過（Redis 異常）", exc_info=True)
        return {}
    headers = {"x-ratelimit-limit-requests": str(limit),
               "x-ratelimit-remaining-requests": str(max(0, limit - count)),
               "x-ratelimit-reset-requests": f"{reset}s"}
    if count > limit:
        raise OpenAIError(429, "rate_limit_exceeded", f"Rate limit reached: {limit} requests per minute.",
                          headers={**headers, "Retry-After": str(reset)})
    return headers


def _quota_key(user_id: int) -> str:
    return f"quota:{user_id}:{date.today():%Y%m}"


def month_used_db(user_id: int) -> int:
    first = date.today().replace(day=1)
    with get_db_context() as db:
        total = (db.query(func.coalesce(func.sum(UsageDaily.prompt_tokens + UsageDaily.completion_tokens), 0))
                 .filter(UsageDaily.user_id == user_id, UsageDaily.date >= first).scalar())
    return int(total or 0)


async def month_used(user_id: int) -> int:
    try:
        redis = get_redis()
        value = await redis.get(_quota_key(user_id))
    except Exception:  # noqa: BLE001
        return await run_in_threadpool(month_used_db, user_id)
    if value is not None:
        return int(value)
    used = await run_in_threadpool(month_used_db, user_id)
    try:
        await redis.set(_quota_key(user_id), used, ex=QUOTA_TTL, nx=True)
    except Exception:  # noqa: BLE001
        pass
    return used


async def check_quota(user_id: int, quota: int) -> None:
    if not quota:
        return
    if await month_used(user_id) >= quota:
        raise OpenAIError(429, "insufficient_quota",
                          "You exceeded your monthly token quota. Ask the administrator to raise it.")


async def add_usage(user_id: int, tokens: int) -> None:
    """請求結束後累加；Redis 沒有這個月的計數時不寫，下次查詢會從資料庫重算（已含這次）。"""
    if tokens <= 0:
        return
    try:
        redis = get_redis()
        key = _quota_key(user_id)
        if await redis.exists(key):
            await redis.incrby(key, tokens)
    except Exception:  # noqa: BLE001
        pass
