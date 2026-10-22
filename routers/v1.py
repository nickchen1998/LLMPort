"""OpenAI 相容的 /v1，以及後台測試台（用登入身分呼叫同一條路徑）。"""
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from models.users import User
from schemas.v1 import ChatRequest, DecisionRequest, EmbeddingRequest
from services import gateway
from services.gateway import Caller
from utils.auth import get_current_user
from utils.db_conn import get_db

router = APIRouter(prefix="/v1", tags=["OpenAI 相容 API"])
playground = APIRouter(prefix="/api/playground", tags=["測試台"])


def api_caller(request: Request, authorization: str | None = Header(None), db: Session = Depends(get_db)) -> Caller:
    return gateway.caller_from_key(db, request, authorization)


def login_caller(user: User = Depends(get_current_user)) -> Caller:
    return gateway.caller_from_user(user)


@router.get("/models", summary="這把金鑰能用的模型")
def models(caller: Caller = Depends(api_caller), db: Session = Depends(get_db)):
    return gateway.list_models(db, caller)


@router.post("/chat/completions", summary="對話（可串流、可帶圖片）")
async def chat(request: Request, body: ChatRequest, caller: Caller = Depends(api_caller), db: Session = Depends(get_db)):
    return await gateway.chat_completions(request, db, body, caller)


@router.post("/embeddings", summary="嵌入")
async def embeddings(request: Request, body: EmbeddingRequest, caller: Caller = Depends(api_caller),
                     db: Session = Depends(get_db)):
    return await gateway.embeddings(request, db, body, caller)


@router.post("/decisions", summary="決策（predicate、choice、score）")
async def decisions(request: Request, body: DecisionRequest, caller: Caller = Depends(api_caller),
                    db: Session = Depends(get_db)):
    return await gateway.decisions(request, db, body, caller)


@playground.post("/chat/completions", summary="測試台：對話")
async def pg_chat(request: Request, body: ChatRequest, caller: Caller = Depends(login_caller), db: Session = Depends(get_db)):
    return await gateway.chat_completions(request, db, body, caller)


@playground.post("/embeddings", summary="測試台：嵌入")
async def pg_embeddings(request: Request, body: EmbeddingRequest, caller: Caller = Depends(login_caller),
                        db: Session = Depends(get_db)):
    return await gateway.embeddings(request, db, body, caller)


@playground.post("/decisions", summary="測試台：決策")
async def pg_decisions(request: Request, body: DecisionRequest, caller: Caller = Depends(login_caller),
                       db: Session = Depends(get_db)):
    return await gateway.decisions(request, db, body, caller)


@playground.get("/models", summary="測試台：我能用的模型")
def pg_models(caller: Caller = Depends(login_caller), db: Session = Depends(get_db)):
    return gateway.list_models(db, caller)
