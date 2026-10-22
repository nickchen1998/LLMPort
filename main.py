"""LLMPort：FastAPI 入口。

- /v1/*  OpenAI 相容 API（金鑰認證）
- /api/* 後台 API（JWT 登入）
- /      Vue 後台建置檔（templates/dist）

模型 worker 的狀態放在這個行程的記憶體裡，所以只能跑一個 uvicorn 行程（不要開 --workers）。
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from models import import_all_models
from models.llm_models import LLMModel
from routers.admins import router as admins_router
from routers.auth import router as auth_router
from routers.me import router as me_router
from routers.members import router as members_router
from routers.models_admin import router as models_router
from routers.system import router as system_router
from routers.usage import router as usage_router
from routers.v1 import playground as playground_router
from routers.v1 import router as v1_router
from services import gateway, metrics, system_settings
from services.model_manager import LoadError, manager
from services.monitor import monitor
from utils.db_conn import get_db_context
from utils.openai_errors import OpenAIError, error_response, is_v1, validation_error
from utils.settings import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("llmport")
import_all_models()


async def _restore_models() -> None:
    """系統設定開了「重新開機後恢復」才會執行；預設關閉（只手動載入）。"""
    with get_db_context() as db:
        values = system_settings.get_all(db)
        if not values.get("restore_on_boot"):
            return
        models = db.query(LLMModel).filter(LLMModel.id.in_(values.get("last_loaded") or [])).all()
    for model in models:
        try:
            host = await run_in_threadpool(metrics.host_snapshot)
            await manager.load(model, manager.memory_budget(host, values))
            logger.info("開機恢復載入 %s", model.api_name)
        except LoadError as e:
            logger.warning("開機恢復 %s 失敗：%s", model.api_name, e)


def _remember_loaded() -> None:
    with get_db_context() as db:
        system_settings.save(db, {"last_loaded": manager.loaded_ids()})


@asynccontextmanager
async def lifespan(_: FastAPI):
    metrics.gpu.start()
    monitor.start()
    try:
        await _restore_models()
    except Exception:  # noqa: BLE001  資料庫還沒準備好時不要讓服務起不來
        logger.exception("開機恢復模型失敗")
    yield
    try:
        _remember_loaded()
    except Exception:  # noqa: BLE001
        logger.exception("記錄已載入的模型失敗")
    await monitor.stop()
    await manager.shutdown()


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan,
              description="在 Mac mini 上以 MLX 部署本地模型，提供 OpenAI 相容 API 與會員、金鑰、監控後台。")

for r in (auth_router, me_router, members_router, admins_router, models_router, usage_router, system_router,
          playground_router, v1_router):
    app.include_router(r)


@app.exception_handler(OpenAIError)
async def openai_error_handler(request: Request, exc: OpenAIError):
    gateway.record_error(request, exc)
    return error_response(exc)


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    if is_v1(request) or request.url.path.startswith("/api/playground/"):
        return error_response(validation_error(exc))
    return await request_validation_exception_handler(request, exc)


@app.middleware("http")
async def host_guard(request: Request, call_next):
    """從 API 網域進來的請求只能用 /v1；後台與 /api 一律 404（cloudflared 也會先擋一次）。"""
    host = (request.headers.get("host") or "").split(":")[0]
    if settings.api_host and host == settings.api_host and not is_v1(request):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    return await call_next(request)


# ─── 後台頁面（npm run build 之後才有） ───

_dist = settings.static_dir
if (_dist / "assets").exists():
    app.mount("/assets", StaticFiles(directory=_dist / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
async def spa(path: str):
    if path.startswith(("api/", "v1/")):
        return JSONResponse({"detail": "Not Found"}, status_code=404)
    file = (_dist / path).resolve()
    if path and file.is_file() and _dist.resolve() in file.parents:
        return FileResponse(file)
    index = _dist / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"detail": "後台頁面還沒建置：cd templates && npm install && npm run build；開發時用 npm run dev"},
                        status_code=404)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.app_host, port=settings.app_port, reload=settings.app_reload,
                log_level="info", proxy_headers=True, forwarded_allow_ips="127.0.0.1")
