"""每 2 秒取樣主機與 worker 狀態，推給後台的 SSE；每 10 秒留一點，保留 15 分鐘。

只有一個 FastAPI 行程，所以訂閱者直接放在記憶體（不像 PTCFormosAI 要經 Redis pub/sub）。
"""
import asyncio
import logging
import time
from collections import deque

from starlette.concurrency import run_in_threadpool

from services import metrics, system_settings, usage
from services.model_manager import manager
from utils.db_conn import get_db_context
from utils.settings import settings

logger = logging.getLogger(__name__)
INTERVAL = 2


def _settings_values() -> dict:
    with get_db_context() as db:
        return system_settings.get_all(db)


class Monitor:
    def __init__(self):
        self.history: deque = deque(maxlen=90)
        self.subscribers: set[asyncio.Queue] = set()
        self.latest: dict | None = None
        self.tunnel = "unknown"
        self._values: dict | None = None
        self._task: asyncio.Task | None = None

    async def snapshot(self, refresh_settings: bool = False) -> dict:
        if refresh_settings or self._values is None:
            self._values = await run_in_threadpool(_settings_values)
        host = await run_in_threadpool(metrics.host_snapshot)
        budget = manager.memory_budget(host, self._values)
        return {"ts": time.time(), "host": host, "budget": budget, "models": manager.snapshot(), "tunnel": self.tunnel}

    async def _loop(self) -> None:
        tick = 0
        while True:
            try:
                await manager.refresh_memory()
                if tick % 5 == 0:
                    self.tunnel = await metrics.cloudflared_status(settings.cloudflared_metrics_url)
                snap = await self.snapshot(refresh_settings=tick % 5 == 0)
                self.latest = snap
                if tick % 5 == 0:
                    self.history.append({"ts": snap["ts"], "system_mb": snap["budget"]["system_mb"],
                                         "models": {mid: m["mem_mb"] for mid, m in snap["models"].items() if m["mem_mb"]}})
                for q in list(self.subscribers):
                    if q.full():
                        q.get_nowait()
                    q.put_nowait(snap)
                if tick % 1800 == 0:
                    removed = await run_in_threadpool(usage.prune_logs, int(self._values.get("retention_days", 90)))
                    if removed:
                        logger.info("清除 %s 筆過期的請求紀錄", removed)
            except Exception:  # noqa: BLE001  監控失敗不能讓迴圈停掉
                logger.exception("監控取樣失敗")
            tick += 1
            await asyncio.sleep(INTERVAL)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=4)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self.subscribers.discard(q)


monitor = Monitor()
