"""模型 worker：由 FastAPI 的模型管理員啟動，一個模型一個行程，只聽 127.0.0.1。

    python -m workers.server --port 9101 --name qwen3-4b --engine mlx-lm --model-path model_files/Qwen3-4B-Instruct-2507-4bit

內部介面（都要帶 X-Worker-Token）：
- GET  /health  載入進度、記憶體
- POST /chat    NDJSON 串流：{"delta"} …，最後 {"done", "finish_reason", "prompt_tokens", "completion_tokens"}
- POST /embed   {"data": [[...]], "prompt_tokens"}
- POST /decide  {"answers": [...], "input_tokens"}

MLX 不保證多執行緒安全，所以載入與所有推論都排進同一條執行緒（一次一個）。
"""
import argparse
import asyncio
import json
import logging
import os
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager

from fastapi import Body, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from workers import decision
from workers.engines.base import Engine, EngineError, normalize

logger = logging.getLogger("llmport.worker")


def make_engine(kind: str, path: str, **kw) -> Engine:
    if kind == "fake":
        from workers.engines.fake import FakeEngine
        return FakeEngine(path, **kw)
    from workers.engines import mlx_engines
    cls = {"mlx-lm": mlx_engines.MLXLMEngine, "mlx-vlm": mlx_engines.MLXVLMEngine,
           "mlx-embeddings": mlx_engines.MLXEmbeddingsEngine}.get(kind)
    if cls is None:
        raise ValueError(f"不認得的引擎 {kind}")
    return cls(path, **kw)


def create_app(engine_factory: Callable[[], Engine], token: str | None = None, eager: bool = False) -> FastAPI:
    """eager=True 時同步載入（測試用，httpx 的 ASGITransport 不會觸發 lifespan）。"""
    state = {"status": "loading", "stage": "啟動中", "error": None, "engine": None}
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="engine")

    def load() -> None:
        try:
            engine = engine_factory()
            engine.load(lambda stage: state.update(stage=stage))
            state["stage"] = "預熱：跑一次短推論"
            engine.warmup()
            state.update(status="ready", stage="", engine=engine)
        except Exception as e:  # noqa: BLE001  載入失敗要回報給管理員，不讓行程默默結束
            logger.exception("載入失敗")
            state.update(status="error", error=str(e) or e.__class__.__name__)

    @asynccontextmanager
    async def lifespan(_):
        if not eager:
            executor.submit(load)
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    if eager:
        load()
    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    def check(x_worker_token: str | None, need_ready: bool = True) -> Engine | None:
        if token and x_worker_token != token:
            raise HTTPException(status_code=401, detail="bad worker token")
        if need_ready and state["status"] != "ready":
            raise HTTPException(status_code=503, detail="model is not ready")
        return state["engine"]

    async def run(fn):
        try:
            return await asyncio.get_running_loop().run_in_executor(executor, fn)
        except EngineError as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    @app.get("/health")
    def health(x_worker_token: str | None = Header(None)):
        engine = check(x_worker_token, need_ready=False)
        active, peak = engine.memory_mb() if engine else (0.0, 0.0)
        return {"status": state["status"], "stage": state["stage"], "error": state["error"],
                "active_mb": round(active, 1), "peak_mb": round(peak, 1)}

    @app.post("/chat")
    async def chat(body: dict = Body(...), x_worker_token: str | None = Header(None)):
        engine = check(x_worker_token)
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        cancelled = threading.Event()

        def produce() -> None:
            put = lambda item: loop.call_soon_threadsafe(queue.put_nowait, item)  # noqa: E731
            try:
                for item in engine.chat_stream(body["messages"], max_tokens=int(body.get("max_tokens") or 1024),
                                               temperature=float(body.get("temperature", 0.7)),
                                               top_p=body.get("top_p"), stop=body.get("stop") or [],
                                               seed=body.get("seed")):
                    if cancelled.is_set():
                        break
                    put(item)
            except EngineError as e:
                put({"error": str(e), "kind": "invalid"})
            except Exception as e:  # noqa: BLE001  錯誤要傳回閘道，換成 OpenAI 格式
                logger.exception("生成失敗")
                put({"error": str(e) or e.__class__.__name__, "kind": "internal"})
            finally:
                put(None)

        executor.submit(produce)

        async def lines():
            try:
                while (item := await queue.get()) is not None:
                    yield json.dumps(item, ensure_ascii=False) + "\n"
            finally:
                cancelled.set()   # 用戶端斷線就停止生成

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.post("/embed")
    async def embed(body: dict = Body(...), x_worker_token: str | None = Header(None)):
        engine = check(x_worker_token)
        result = await run(lambda: engine.embed(list(body["input"])))
        if isinstance(result, JSONResponse):
            return result
        vectors, tokens = result
        if body.get("dimensions"):
            vectors = [normalize(v[:int(body["dimensions"])]) for v in vectors]
        return {"data": vectors, "prompt_tokens": tokens}

    @app.post("/decide")
    async def decide(body: dict = Body(...), x_worker_token: str | None = Header(None)):
        engine = check(x_worker_token)
        result = await run(lambda: decision.decide(engine, body["input"], body["questions"]))
        if isinstance(result, JSONResponse):
            return result
        answers, tokens = result
        return {"answers": answers, "input_tokens": tokens}

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="LLMPort 模型 worker")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--engine", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--context-length", type=int, default=32768)
    parser.add_argument("--dims", type=int)
    parser.add_argument("--simulated-mb", type=float, default=0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s worker: %(message)s")

    kw = {"context_length": args.context_length, "dims": args.dims}
    if args.engine == "fake":
        kw.update(name=args.name, simulated_mb=args.simulated_mb)
    app = create_app(lambda: make_engine(args.engine, args.model_path, **kw), token=os.getenv("LLMPORT_WORKER_TOKEN"))

    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
