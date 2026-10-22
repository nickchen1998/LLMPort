"""模型管理（只給管理者）：管理員可以載入、卸載；新增、修改、刪除與下載只給 Superuser。"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from models.llm_models import Capability, DownloadStatus, Engine, LLMModel
from models.users import User
from schemas.admin import ModelCreate, ModelUpdate
from services import audit, downloads, metrics, system_settings
from services.accounts import bad_request
from services.catalog import model_out
from services.model_manager import LoadError, manager, worker_log_tail
from utils.auth import require_admin, require_superuser
from utils.db_conn import get_db
from utils.settings import settings

router = APIRouter(prefix="/api", tags=["模型管理"])


def _model(db: Session, model_id: int) -> LLMModel:
    model = db.get(LLMModel, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到這個模型")
    return model


async def _budget(db: Session) -> dict:
    host = await run_in_threadpool(metrics.host_snapshot)
    return manager.memory_budget(host, system_settings.get_all(db))


def _check_caps(caps: list[str]) -> None:
    unknown = set(caps) - set(Capability.ALL)
    if unknown:
        raise bad_request(f"不認得的能力：{'、'.join(sorted(unknown))}")


@router.get("/models", summary="模型清單（含執行狀態與載入檢查）")
async def list_models(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    budget = await _budget(db)
    models = db.query(LLMModel).order_by(LLMModel.id).all()
    return {"budget": budget, "fake_workers": settings.fake_workers, "model_dir": str(settings.model_dir),
            "models": [model_out(m, manager.get(m.id).public(), manager.load_check(m, budget)) for m in models]}


@router.get("/models/{model_id}/load-check", summary="載入前的記憶體檢查")
async def load_check(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = _model(db, model_id)
    budget = await _budget(db)
    return {"budget": budget, "check": manager.load_check(model, budget)}


@router.post("/models/{model_id}/load", summary="載入模型（啟動 worker 行程）")
async def load_model(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = _model(db, model_id)
    if not model.is_enabled:
        raise bad_request("這個模型已停用，請先啟用")
    try:
        rt = await manager.load(model, await _budget(db))
    except LoadError as e:
        raise bad_request(str(e))
    audit.record(db, admin, "載入模型", model.api_name)
    return rt.public()


@router.post("/models/{model_id}/unload", summary="卸載模型（結束 worker 行程）")
async def unload_model(model_id: int, mode: str = Query("drain", pattern="^(drain|now)$"),
                       admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    model = _model(db, model_id)
    try:
        rt = await manager.unload(model.id, mode)
    except LoadError as e:
        raise bad_request(str(e))
    audit.record(db, admin, "立即卸載模型" if mode == "now" else "卸載模型", model.api_name)
    return rt.public()


@router.get("/models/{model_id}/log", summary="worker log 最後幾行")
def model_log(model_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    _model(db, model_id)
    return {"log": worker_log_tail(manager.get(model_id))}


@router.post("/models", status_code=status.HTTP_201_CREATED, summary="登記模型（預設接著從 Hugging Face 下載）")
def create_model(body: ModelCreate, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    _check_caps(body.capabilities)
    engine = body.resolved_engine()
    if engine not in Engine.ALL:
        raise bad_request(f"不認得的引擎 {engine}")
    if db.query(LLMModel).filter(LLMModel.api_name == body.api_name).first():
        raise bad_request("API 名稱已經有人用了")
    quant = "4-bit" if "4bit" in body.source_repo else "8-bit" if "8bit" in body.source_repo else None
    model = LLMModel(api_name=body.api_name, display_name=body.display_name or body.source_repo.split("/")[-1],
                     source_repo=body.source_repo, engine=engine, capabilities=body.capabilities, quant=quant,
                     context_length=body.context_length, embedding_dims=body.embedding_dims, est_kv_mb=body.est_kv_mb,
                     default_max_tokens=0 if Capability.EMBEDDING in body.capabilities else 1024, aliases=[])
    db.add(model)
    db.flush()
    audit.record(db, su, "新增模型", model.api_name, commit=False)
    db.commit()
    if body.start_download:
        downloads.start(model.id)
        db.refresh(model)
    return model_out(model, manager.get(model.id).public())


@router.post("/models/{model_id}/download", summary="下載（或重新下載）模型檔")
def download_model(model_id: int, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    model = _model(db, model_id)
    if manager.get(model.id).is_up:
        raise bad_request("模型載入中，請先卸載再重新下載")
    if not downloads.start(model.id):
        raise bad_request("已經在下載了")
    audit.record(db, su, "下載模型", model.source_repo)
    db.refresh(model)
    return model_out(model, manager.get(model.id).public())


@router.patch("/models/{model_id}", summary="修改模型設定")
def update_model(model_id: int, body: ModelUpdate, su: User = Depends(require_superuser), db: Session = Depends(get_db)):
    model = _model(db, model_id)
    data = body.model_dump(exclude_unset=True)
    if "capabilities" in data:
        _check_caps(data["capabilities"])
    if "aliases" in data:
        aliases = [a.strip() for a in data["aliases"] if a and a.strip()]
        taken = {a for m in db.query(LLMModel).filter(LLMModel.id != model.id).all() for a in [m.api_name, *(m.aliases or [])]}
        clash = [a for a in aliases if a in taken]
        if clash:
            raise bad_request(f"別名已經被其他模型使用：{'、'.join(clash)}")
        data["aliases"] = aliases
    for field, value in data.items():
        setattr(model, field, value)
    audit.record(db, su, "修改模型設定", model.api_name, detail=data, commit=False)
    db.commit()
    return model_out(model, manager.get(model.id).public())


@router.delete("/models/{model_id}", summary="刪除模型（要先卸載）")
def delete_model(model_id: int, delete_files: bool = True, su: User = Depends(require_superuser),
                 db: Session = Depends(get_db)):
    model = _model(db, model_id)
    if manager.get(model.id).is_up:
        raise bad_request("請先卸載模型")
    if model.download_status == DownloadStatus.DOWNLOADING:
        raise bad_request("下載中，請等下載結束再刪除")
    removed = downloads.delete_files(model) if delete_files else False
    audit.record(db, su, "刪除模型", model.api_name, detail={"files_removed": removed}, commit=False)
    db.delete(model)
    db.commit()
    manager.runtimes.pop(model_id, None)
    return {"deleted": True, "files_removed": removed}
