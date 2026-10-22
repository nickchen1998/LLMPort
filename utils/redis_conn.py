"""Redis 連線（限流與本月用量計數）。測試以 set_redis 換成 fakeredis。"""
import redis.asyncio as aioredis

from utils.settings import settings

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


def set_redis(client: aioredis.Redis | None) -> None:
    global _client
    _client = client
