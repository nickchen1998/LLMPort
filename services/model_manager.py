"""模型 worker 管理：一個模型一個子行程，載入＝啟動行程，卸載＝結束行程。

- 只手動載入與卸載。沒載入的模型被呼叫時 /v1 回 503 model_not_loaded，這裡不會自動載入，也不會擠掉別的模型。
- 結束行程是最可靠的釋放方式：Python 與 MLX 的快取不會殘留，worker 當掉也不會拖垮 FastAPI。
- 狀態放在 FastAPI 行程的記憶體，所以 uvicorn 只能開一個行程。
- worker 只綁 127.0.0.1，另外用每次啟動時隨機產生的 token 驗證，避免本機其他程式直接呼叫。
- FAKE_WORKERS=true 且沒有模型檔時改用假 worker：一樣是真的子行程，只是回覆與記憶體是模擬的。
"""
import asyncio
import logging
import os
import secrets
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from models.llm_models import DownloadStatus, LLMModel
from utils.settings import ROOT, settings

logger = logging.getLogger(__name__)

UP_STATUSES = ("loading", "loaded", "unloading")


class LoadError(Exception):
    """載入或卸載前的檢查沒過；訊息直接顯示在畫面上。"""


class ModelBusy(Exception):
    """佇列滿了。"""


@dataclass
class Runtime:
    model_id: int
    api_name: str = ""
    status: str = "unloaded"        # unloaded | loading | loaded | unloading | error
    stage: str = ""
    error: str | None = None
    pid: int | None = None
    port: int | None = None
    fake: bool = False
    loaded_at: float | None = None
    mem_mb: float = 0.0
    peak_mb: float = 0.0
    active: int = 0
    waiting: int = 0
    concurrency: int = 1
    queue_max: int = 8
    tps: float = 0.0
    ttft_ms: float = 0.0
    log_path: str | None = None
    token: str = field(default="", repr=False)
    proc: asyncio.subprocess.Process | None = field(default=None, repr=False)
    sem: asyncio.Semaphore | None = field(default=None, repr=False)
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)

    @property
    def is_up(self) -> bool:
        return self.status in UP_STATUSES

    def public(self) -> dict:
        return {"model_id": self.model_id, "api_name": self.api_name, "status": self.status, "stage": self.stage,
                "error": self.error,
                "pid": self.pid, "port": self.port, "fake": self.fake, "loaded_at": self.loaded_at,
                "mem_mb": round(self.mem_mb, 1), "peak_mb": round(self.peak_mb, 1), "active": self.active,
                "waiting": self.waiting, "concurrency": self.concurrency, "queue_max": self.queue_max,
                "tps": round(self.tps, 1), "ttft_ms": round(self.ttft_ms)}


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class ModelManager:
    def __init__(self):
        self.runtimes: dict[int, Runtime] = {}

    # ─── 狀態 ───

    def get(self, model_id: int) -> Runtime:
        rt = self.runtimes.get(model_id)
        if rt is None:
            rt = self.runtimes[model_id] = Runtime(model_id=model_id)
        return rt

    def snapshot(self) -> dict[int, dict]:
        return {mid: rt.public() for mid, rt in self.runtimes.items()}

    def loaded_ids(self) -> list[int]:
        return [mid for mid, rt in self.runtimes.items() if rt.status == "loaded"]

    def memory_budget(self, host: dict, values: dict) -> dict:
        """可再載入 = min(Metal 上限 − 已載入模型, 可用記憶體 − 安全餘裕)。

        假 worker 的記憶體是模擬的，所以從可用記憶體扣掉，讓開發時的記憶體檢查跟正式環境一樣。
        """
        models = sum(rt.mem_mb for rt in self.runtimes.values() if rt.is_up)
        fake = sum(rt.mem_mb for rt in self.runtimes.values() if rt.is_up and rt.fake)
        available = max(0.0, host["available_mb"] - fake)
        metal_limit = float(values["metal_limit_gb"]) * 1024
        headroom = float(values["headroom_gb"]) * 1024
        return {
            "total_mb": host["total_mb"],
            "available_mb": available,
            "system_mb": max(0.0, host["total_mb"] - host["available_mb"] - (models - fake)),
            "models_mb": models,
            "metal_limit_mb": metal_limit,
            "headroom_mb": headroom,
            "can_load_mb": max(0.0, min(metal_limit - models, available - headroom)),
        }

    @staticmethod
    def files_ready(model: LLMModel) -> bool:
        return model.download_status == DownloadStatus.DOWNLOADED and model.files_path(settings.model_dir).exists()

    def load_check(self, model: LLMModel, budget: dict) -> dict:
        need = float(model.est_mb)
        files = self.files_ready(model)
        fake = not files and settings.fake_workers
        metal_after = budget["models_mb"] + need
        phys_left = budget["available_mb"] - need
        metal_ok = metal_after <= budget["metal_limit_mb"]
        phys_ok = phys_left >= budget["headroom_mb"]
        reason = None
        if not files and not fake:
            reason = "模型檔還沒下載，請先下載"
        elif not (metal_ok and phys_ok):
            reason = "記憶體不夠"
        suggest = None
        if (files or fake) and not (metal_ok and phys_ok):
            fits = []
            for mid, rt in self.runtimes.items():
                if rt.status != "loaded" or mid == model.id:
                    continue
                if (budget["models_mb"] - rt.mem_mb + need <= budget["metal_limit_mb"]
                        and budget["available_mb"] + rt.mem_mb - need >= budget["headroom_mb"]):
                    fits.append(rt)
            if fits:
                best = min(fits, key=lambda r: r.mem_mb)
                suggest = {"model_id": best.model_id, "api_name": best.api_name, "mem_mb": round(best.mem_mb)}
        return {"need_mb": need, "metal_after_mb": metal_after, "metal_limit_mb": budget["metal_limit_mb"],
                "phys_left_mb": phys_left, "headroom_mb": budget["headroom_mb"], "metal_ok": metal_ok,
                "phys_ok": phys_ok, "files_ready": files, "fake": fake, "ok": reason is None, "reason": reason,
                "suggest": suggest}

    # ─── 載入與卸載 ───

    async def load(self, model: LLMModel, budget: dict) -> Runtime:
        rt = self.get(model.id)
        if rt.is_up:
            raise LoadError(f"{model.api_name} 已經在載入或執行中")
        check = self.load_check(model, budget)
        if not check["ok"]:
            raise LoadError(check["reason"])
        port = settings.worker_port_base + model.id
        if not _port_free(port):
            raise LoadError(f"port {port} 被其他程式占用，請先關掉它，或調整 WORKER_PORT_BASE")
        spec = {"api_name": model.api_name, "engine": model.engine, "path": str(model.files_path(settings.model_dir)),
                "ctx": model.context_length, "dims": model.embedding_dims, "est_mb": model.est_mb}
        self._reset(rt)
        rt.api_name = model.api_name
        rt.status, rt.stage = "loading", "啟動 worker 行程"
        rt.port, rt.fake, rt.token = port, check["fake"], secrets.token_urlsafe(24)
        rt.concurrency, rt.queue_max = max(1, model.concurrency), max(0, model.queue_max)
        rt.sem = asyncio.Semaphore(rt.concurrency)
        asyncio.create_task(self._run(rt, spec))
        return rt

    async def _run(self, rt: Runtime, spec: dict) -> None:
        log_path = settings.tmp_dir / "logs" / f"worker-{spec['api_name']}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rt.log_path = str(log_path)
        cmd = [sys.executable, "-m", "workers.server", "--port", str(rt.port), "--name", spec["api_name"],
               "--engine", "fake" if rt.fake else spec["engine"], "--model-path", spec["path"],
               "--context-length", str(spec["ctx"])]
        if spec["dims"]:
            cmd += ["--dims", str(spec["dims"])]
        if rt.fake:
            cmd += ["--simulated-mb", str(spec["est_mb"])]
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "PYTHONUNBUFFERED": "1",
               "LLMPORT_WORKER_TOKEN": rt.token}
        try:
            with open(log_path, "ab") as log:
                rt.proc = await asyncio.create_subprocess_exec(*cmd, cwd=str(ROOT), env=env, stdout=log,
                                                               stderr=asyncio.subprocess.STDOUT)
        except OSError as e:
            self._fail(rt, f"無法啟動 worker：{e}")
            return
        rt.pid = rt.proc.pid
        logger.info("啟動 worker %s（PID %s、port %s%s）", spec["api_name"], rt.pid, rt.port, "、假 worker" if rt.fake else "")
        deadline = time.monotonic() + settings.worker_load_timeout
        async with self.client(rt, timeout=2) as client:
            while True:
                if rt.status != "loading":
                    return
                if rt.proc.returncode is not None:
                    self._fail(rt, f"worker 結束了（exit code {rt.proc.returncode}），詳見 {log_path.name}")
                    return
                if time.monotonic() > deadline:
                    await self._terminate(rt)
                    self._fail(rt, "載入逾時")
                    return
                try:
                    health = (await client.get("/health")).json()
                except (httpx.HTTPError, ValueError):
                    health = None
                if health:
                    rt.stage = health.get("stage") or rt.stage
                    self._apply_memory(rt, health)
                    if health.get("status") == "ready":
                        rt.status, rt.stage, rt.loaded_at = "loaded", "", time.time()
                        logger.info("worker %s 載入完成", spec["api_name"])
                        break
                    if health.get("status") == "error":
                        await self._terminate(rt)
                        self._fail(rt, health.get("error") or "載入失敗")
                        return
                await asyncio.sleep(.5)
        code = await rt.proc.wait()
        if rt.status == "loaded":
            self._fail(rt, f"worker 意外結束（exit code {code}），詳見 {log_path.name}")

    async def unload(self, model_id: int, mode: str = "drain") -> Runtime:
        rt = self.get(model_id)
        if rt.status == "loading":
            rt.status = "unloading"
            await self._terminate(rt)
            self._reset(rt)
            return rt
        if rt.status != "loaded":
            raise LoadError("模型沒有載入")
        rt.status = "unloading"
        asyncio.create_task(self._unload(rt, mode))
        return rt

    async def _unload(self, rt: Runtime, mode: str) -> None:
        if mode == "drain":
            deadline = time.monotonic() + 120
            while (rt.active or rt.waiting) and time.monotonic() < deadline:
                await asyncio.sleep(.2)
        await self._terminate(rt)
        logger.info("worker %s 已卸載", rt.api_name)
        self._reset(rt)

    async def _terminate(self, rt: Runtime) -> None:
        proc = rt.proc
        if proc is None or proc.returncode is not None:
            return
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), 10)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    async def shutdown(self) -> None:
        for rt in list(self.runtimes.values()):
            if rt.proc is not None:
                await self._terminate(rt)

    def _reset(self, rt: Runtime) -> None:
        rt.status, rt.stage, rt.error = "unloaded", "", None
        rt.pid = rt.proc = rt.loaded_at = None
        rt.mem_mb = rt.peak_mb = 0.0
        rt.active = rt.waiting = 0

    def _fail(self, rt: Runtime, message: str) -> None:
        logger.warning("worker %s：%s", rt.api_name, message)
        rt.status, rt.error, rt.stage = "error", message, ""
        rt.pid, rt.mem_mb, rt.active, rt.waiting = None, 0.0, 0, 0

    @staticmethod
    def _apply_memory(rt: Runtime, health: dict) -> None:
        if health.get("active_mb") is not None:
            rt.mem_mb = float(health["active_mb"])
        if health.get("peak_mb") is not None:
            rt.peak_mb = max(rt.peak_mb, float(health["peak_mb"]))

    async def refresh_memory(self) -> None:
        """監控取樣時順便問一下每個 worker 用了多少記憶體。"""
        for rt in list(self.runtimes.values()):
            if rt.status != "loaded":
                continue
            try:
                async with self.client(rt, timeout=1) as client:
                    self._apply_memory(rt, (await client.get("/health")).json())
            except (httpx.HTTPError, ValueError):
                pass

    # ─── 呼叫 worker ───

    def client(self, rt: Runtime, timeout: float | None = None) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=f"http://127.0.0.1:{rt.port}", transport=rt.transport,
                                 headers={"X-Worker-Token": rt.token}, timeout=httpx.Timeout(timeout, connect=5))

    async def acquire(self, rt: Runtime) -> None:
        """取得處理名額；佇列滿了丟 ModelBusy。"""
        if rt.sem is None:
            rt.sem = asyncio.Semaphore(rt.concurrency)
        if rt.sem.locked() and rt.waiting >= rt.queue_max:
            raise ModelBusy()
        rt.waiting += 1
        try:
            await rt.sem.acquire()
        finally:
            rt.waiting -= 1
        rt.active += 1

    def release(self, rt: Runtime) -> None:
        rt.active = max(0, rt.active - 1)
        if rt.sem is not None:
            rt.sem.release()

    @staticmethod
    def record_speed(rt: Runtime, tps: float | None, ttft_ms: float | None) -> None:
        if tps:
            rt.tps = tps if not rt.tps else rt.tps * .7 + tps * .3
        if ttft_ms:
            rt.ttft_ms = ttft_ms if not rt.ttft_ms else rt.ttft_ms * .7 + ttft_ms * .3

    # ─── 測試用 ───

    def attach_test_worker(self, model: LLMModel, transport: httpx.AsyncBaseTransport, mem_mb: float = 0) -> Runtime:
        """測試直接接上 ASGI 的假 worker，不啟動子行程。"""
        rt = self.get(model.id)
        self._reset(rt)
        rt.api_name, rt.status, rt.transport, rt.port = model.api_name, "loaded", transport, 0
        rt.concurrency, rt.queue_max, rt.mem_mb, rt.fake = max(1, model.concurrency), model.queue_max, mem_mb, True
        rt.sem = asyncio.Semaphore(rt.concurrency)
        return rt


manager = ModelManager()


def worker_log_tail(rt: Runtime, lines: int = 40) -> str:
    if not rt.log_path:
        return ""
    try:
        return "\n".join(Path(rt.log_path).read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""
