"""系統監控、系統設定與健康檢查。"""
import asyncio
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from models.users import User
from services import audit, system_settings
from services.monitor import monitor
from utils.auth import get_user_from_token_param, require_admin, require_superuser
from utils.db_conn import get_db
from utils.settings import settings

router = APIRouter(prefix="/api", tags=["系統"])


@router.get("/health", summary="健康檢查")
def health():
    return {"status": "ok", "app": settings.app_name}


@router.get("/system/snapshot", summary="目前的主機與 worker 狀態")
async def snapshot(admin: User = Depends(require_admin)):
    return monitor.latest or await monitor.snapshot(refresh_settings=True)


@router.get("/system/history", summary="近 15 分鐘的記憶體組成（每 10 秒一點）")
def history(admin: User = Depends(require_admin)):
    return list(monitor.history)


@router.get("/system/stream", summary="SSE：每 2 秒推一次狀態（EventSource 用 ?token= 帶 JWT）")
async def stream(request: Request, user: User = Depends(get_user_from_token_param)):
    if not user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理者權限")
    queue = monitor.subscribe()

    async def events():
        try:
            if monitor.latest:
                yield "data: " + json.dumps(monitor.latest) + "\n\n"
            while not await request.is_disconnected():
                try:
                    snap = await asyncio.wait_for(queue.get(), timeout=15)
                    yield "data: " + json.dumps(snap) + "\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            monitor.unsubscribe(queue)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/settings", summary="系統設定")
def get_settings(su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    values = system_settings.get_all(db)
    return {"values": {k: values[k] for k in system_settings.EDITABLE},
            "defaults": {k: v for k, v in system_settings.defaults().items() if k in system_settings.EDITABLE},
            "env": {"api_host": settings.api_host, "console_host": settings.console_host,
                    "public_api_base": settings.public_api_base, "model_dir": str(settings.model_dir),
                    "fake_workers": settings.fake_workers}}


@router.put("/settings", summary="修改系統設定")
def put_settings(changes: dict = Body(...), su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    try:
        clean = system_settings.validate(changes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    system_settings.save(db, clean, su.id)
    audit.record(db, su, "修改系統設定", ", ".join(clean), detail=clean)
    return get_settings(su, db)


@router.get("/public-config", summary="前端需要的公開設定（不用登入）")
def public_config():
    return {"app_name": settings.app_name, "public_api_base": settings.public_api_base}
