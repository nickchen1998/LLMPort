"""/v1 閘道（測試台也走這裡）。一個請求依序經過：

1. 驗證金鑰（雜湊比對）→ 401 invalid_api_key
2. 會員與金鑰狀態（停用、過期）→ 403 key_disabled
3. 解析模型與權限（別名 → 實際模型）→ 404 model_not_found
4. 限流與本月配額（Redis）→ 429 rate_limit_exceeded／insufficient_quota
5. 模型已載入？（只手動載入）→ 503 model_not_loaded
6. 排入佇列 → 503 model_busy
7. 轉給 worker 並回傳（對話可串流）→ 502 worker_error
8. 記錄用量（回應送出後才寫，不增加延遲）
"""
import asyncio
import base64
import json
import logging
import secrets
import struct
import time
from dataclasses import dataclass

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from models.llm_models import Capability, LLMModel
from models.usage import Source
from models.users import ApiKey, User
from schemas.v1 import ChatRequest, DecisionRequest, EmbeddingRequest
from services import limits, usage
from services.model_manager import ModelBusy, Runtime, manager
from utils.api_key import API_KEY_PREFIX, hash_api_key
from utils.openai_errors import (OpenAIError, invalid_api_key, key_disabled, model_busy, model_not_found,
                                 model_not_loaded, unsupported)

logger = logging.getLogger(__name__)
_pending: set[asyncio.Task] = set()


@dataclass
class Caller:
    user_id: int
    email: str
    quota: int                  # 本月 token 上限，0 表示不限
    rpm: int
    key_id: int | None          # None 表示從測試台呼叫
    model_ids: set[int] | None  # None 表示不限（管理者在測試台）
    source: str
    rate_bucket: str


def caller_from_key(db: Session, request: Request, authorization: str | None) -> Caller:
    parts = (authorization or "").split()
    raw = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
    if not raw.startswith(API_KEY_PREFIX):
        raise invalid_api_key()
    key = db.query(ApiKey).filter(ApiKey.hashed_key == hash_api_key(raw)).first()
    if key is None or key.is_revoked or key.user is None:
        raise invalid_api_key()
    user = key.user
    request.state.who = {"user_id": user.id, "api_key_id": key.id}
    if not user.is_active:
        raise key_disabled("Your account has been disabled.")
    if key.is_expired():
        raise key_disabled("This API key has expired.")
    return Caller(user_id=user.id, email=user.email, quota=user.monthly_token_quota, rpm=key.effective_rpm(),
                  key_id=key.id, model_ids=key.effective_model_ids(), source=Source.API, rate_bucket=f"k{key.id}")


def caller_from_user(user: User) -> Caller:
    if user.is_admin:
        return Caller(user_id=user.id, email=user.email, quota=0, rpm=600, key_id=None, model_ids=None,
                      source=Source.PLAYGROUND, rate_bucket=f"u{user.id}")
    return Caller(user_id=user.id, email=user.email, quota=user.monthly_token_quota, rpm=user.rpm_limit, key_id=None,
                  model_ids={m.id for m in user.allowed_models}, source=Source.PLAYGROUND, rate_bucket=f"u{user.id}")


@dataclass
class Target:
    model_id: int
    api_name: str
    capabilities: list[str]
    default_max_tokens: int
    embedding_dims: int | None


def resolve_model(db: Session, name: str, caller: Caller, capability: str) -> Target:
    model = None
    for m in db.query(LLMModel).filter(LLMModel.is_enabled.is_(True)).all():
        if m.api_name == name or name in (m.aliases or []):
            model = m
            break
    if model is None or (caller.model_ids is not None and model.id not in caller.model_ids):
        raise model_not_found(name)
    if not model.has(capability):
        what = {"chat": "chat completions", "embedding": "embeddings", "decision": "decisions"}[capability]
        raise unsupported(f"Model '{model.api_name}' does not support {what}.", "model")
    return Target(model.id, model.api_name, list(model.capabilities or []), model.default_max_tokens,
                  model.embedding_dims)


def list_models(db: Session, caller: Caller) -> dict:
    data = []
    for m in db.query(LLMModel).filter(LLMModel.is_enabled.is_(True)).order_by(LLMModel.id).all():
        if caller.model_ids is not None and m.id not in caller.model_ids:
            continue
        data.append({"id": m.api_name, "object": "model", "created": int(m.created_at.timestamp()), "owned_by": "llmport",
                     "loaded": manager.get(m.id).status == "loaded", "capabilities": list(m.capabilities or [])})
    return {"object": "list", "data": data}


# ─── 一次呼叫的紀錄 ───

class Call:
    def __init__(self, request: Request, caller: Caller, endpoint: str, model_name: str, stream: bool = False):
        self.request_id = "req_" + secrets.token_hex(8)
        self.t0 = time.monotonic()
        self.caller = caller
        self.endpoint = endpoint
        self.model_name = model_name
        self.model_id: int | None = None
        self.stream = stream
        self.has_image = False
        self.country = request.headers.get("cf-ipcountry")
        self.user_agent = (request.headers.get("user-agent") or "")[:300]
        self.headers: dict = {}
        self.done = False
        request.state.call = self

    def finish(self, status: int, error_code: str | None = None, prompt: int = 0, completion: int = 0,
               ttft_ms: float | None = None) -> None:
        if self.done:
            return
        self.done = True
        entry = {"request_id": self.request_id, "user_id": self.caller.user_id, "api_key_id": self.caller.key_id,
                 "model_id": self.model_id, "model_name": self.model_name[:100] if self.model_name else None,
                 "endpoint": self.endpoint, "status_code": status, "error_code": error_code, "prompt_tokens": prompt,
                 "completion_tokens": completion, "ttft_ms": round(ttft_ms) if ttft_ms is not None else None,
                 "duration_ms": round((time.monotonic() - self.t0) * 1000), "stream": self.stream,
                 "has_image": self.has_image, "source": self.caller.source, "client_country": self.country,
                 "user_agent": self.user_agent}
        spawn(_save(entry, self.caller.user_id, prompt + completion if status < 400 else 0))


async def _save(entry: dict, user_id: int | None, tokens: int) -> None:
    try:
        await run_in_threadpool(usage.record_request, entry)
        if user_id:
            await limits.add_usage(user_id, tokens)
    except Exception:  # noqa: BLE001  記錄失敗不能影響回應
        logger.exception("用量記錄失敗")


def spawn(coro) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _pending.add(task)
    task.add_done_callback(_pending.discard)


async def drain() -> None:
    """等背景的用量記錄寫完（測試用）。"""
    while _pending:
        await asyncio.gather(*list(_pending), return_exceptions=True)


def record_error(request: Request, err: OpenAIError) -> None:
    """OpenAI 錯誤的例外處理器呼叫：已經建立 Call 的照常記錄；還沒建立的（例如金鑰錯）只記 request_log。"""
    call = getattr(request.state, "call", None)
    if call is not None:
        call.finish(err.status, err.code)
        return
    if not request.url.path.startswith("/v1/"):
        return
    who = getattr(request.state, "who", {}) or {}
    entry = {"request_id": "req_" + secrets.token_hex(8), "user_id": who.get("user_id"), "api_key_id": who.get("api_key_id"),
             "endpoint": request.url.path.removeprefix("/v1/"), "status_code": err.status, "error_code": err.code,
             "source": Source.API, "client_country": request.headers.get("cf-ipcountry"),
             "user_agent": (request.headers.get("user-agent") or "")[:300]}
    spawn(_save(entry, None, 0))


# ─── 共用步驟 ───

async def prepare(call: Call, target: Target) -> Runtime:
    call.model_id = target.model_id
    call.headers = await limits.check_rate(call.caller.rate_bucket, call.caller.rpm)
    await limits.check_quota(call.caller.user_id, call.caller.quota)
    rt = manager.get(target.model_id)
    if rt.status != "loaded":
        raise model_not_loaded(target.api_name)
    try:
        await manager.acquire(rt)
    except ModelBusy:
        raise model_busy(target.api_name)
    if rt.status != "loaded":
        manager.release(rt)
        raise model_not_loaded(target.api_name)
    return rt


def _headers(call: Call) -> dict:
    return {**call.headers, "x-request-id": call.request_id}


def _worker_error(detail: str) -> OpenAIError:
    return OpenAIError(502, "worker_error", f"Model worker error: {detail}"[:500])


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"


def _has_image(messages) -> bool:
    return any(isinstance(m.content, list) and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m.content)
               for m in messages)


# ─── 對話 ───

async def chat_completions(request: Request, db: Session, body: ChatRequest, caller: Caller):
    call = Call(request, caller, "chat/completions", body.model, stream=body.stream)
    target = resolve_model(db, body.model, caller, Capability.CHAT)
    call.model_id = target.model_id
    call.has_image = _has_image(body.messages)
    if call.has_image and Capability.VISION not in target.capabilities:
        raise unsupported(f"Model '{target.api_name}' does not support image input.", "messages")
    if body.tools:
        raise unsupported("Tool calling is not supported yet.", "tools", code="unsupported_parameter")
    if body.response_format and body.response_format.get("type") not in (None, "text"):
        raise unsupported("Only response_format type 'text' is supported for now.", "response_format",
                          code="unsupported_parameter")
    if body.n and body.n > 1:
        raise unsupported("Only n=1 is supported.", "n", code="unsupported_parameter")
    payload = {"messages": [m.model_dump(include={"role", "content"}) for m in body.messages],
               "max_tokens": body.max_completion_tokens or body.max_tokens or target.default_max_tokens,
               "temperature": 0.7 if body.temperature is None else body.temperature, "top_p": body.top_p,
               "stop": [body.stop] if isinstance(body.stop, str) else (body.stop or []), "seed": body.seed}
    rt = await prepare(call, target)
    cid, created = "chatcmpl-" + secrets.token_hex(12), int(time.time())
    if body.stream:
        include_usage = bool((body.stream_options or {}).get("include_usage"))
        released = False

        def release_once() -> None:
            nonlocal released
            if not released:
                released = True
                manager.release(rt)

        async def cleanup() -> None:
            # 用戶端在串流開始前就斷線時，產生器不會執行，名額要在這裡還回去
            release_once()
            call.finish(499, "client_closed")

        return StreamingResponse(_stream_chat(rt, payload, call, cid, created, target.api_name, include_usage, release_once),
                                 media_type="text/event-stream", background=BackgroundTask(cleanup),
                                 headers={**_headers(call), "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
    try:
        text, finish, prompt, completion, ttft = await _collect_chat(rt, payload, call)
    finally:
        manager.release(rt)
    call.finish(200, None, prompt, completion, ttft)
    return JSONResponse({
        "id": cid, "object": "chat.completion", "created": created, "model": target.api_name,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": text}, "finish_reason": finish}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion},
    }, headers=_headers(call))


async def _worker_lines(rt: Runtime, payload: dict):
    async with manager.client(rt) as client:
        async with client.stream("POST", "/chat", json=payload) as resp:
            if resp.status_code != 200:
                raise _worker_error(f"HTTP {resp.status_code}")
            async for line in resp.aiter_lines():
                if line:
                    item = json.loads(line)
                    if "error" in item:
                        if item.get("kind") == "invalid":
                            raise OpenAIError(400, "invalid_request_error", item["error"])
                        raise _worker_error(item["error"])
                    yield item


async def _collect_chat(rt: Runtime, payload: dict, call: Call):
    parts, finish, prompt, completion, ttft = [], "stop", 0, 0, None
    start = time.monotonic()
    try:
        async for item in _worker_lines(rt, payload):
            if item.get("done"):
                finish, prompt, completion = item["finish_reason"], item["prompt_tokens"], item["completion_tokens"]
                break
            if ttft is None:
                ttft = (time.monotonic() - start) * 1000
            parts.append(item.get("delta", ""))
    except httpx.HTTPError as e:
        raise _worker_error(str(e) or e.__class__.__name__)
    _record_speed(rt, completion, ttft, start)
    return "".join(parts), finish, prompt, completion, ttft


def _record_speed(rt: Runtime, completion: int, ttft: float | None, start: float) -> None:
    gen_seconds = time.monotonic() - start - (ttft or 0) / 1000
    manager.record_speed(rt, completion / gen_seconds if completion > 1 and gen_seconds > 0 else None, ttft)


async def _stream_chat(rt: Runtime, payload: dict, call: Call, cid: str, created: int, model: str, include_usage: bool,
                       release):
    base = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model}
    status, code, finish, prompt, completion, ttft = 200, None, "stop", 0, 0, None
    start = time.monotonic()
    try:
        yield _sse({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
        async for item in _worker_lines(rt, payload):
            if item.get("done"):
                finish, prompt, completion = item["finish_reason"], item["prompt_tokens"], item["completion_tokens"]
                break
            if ttft is None:
                ttft = (time.monotonic() - start) * 1000
            yield _sse({**base, "choices": [{"index": 0, "delta": {"content": item.get("delta", "")}, "finish_reason": None}]})
        yield _sse({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]})
        if include_usage:
            yield _sse({**base, "choices": [],
                        "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion}})
        yield "data: [DONE]\n\n"
    except (OpenAIError, httpx.HTTPError, ValueError) as e:
        err = e if isinstance(e, OpenAIError) else _worker_error(str(e) or e.__class__.__name__)
        status, code = err.status, err.code
        yield _sse(err.body())
        yield "data: [DONE]\n\n"
    finally:
        release()
        _record_speed(rt, completion, ttft, start)
        call.finish(status, code, prompt, completion, ttft)


# ─── 嵌入 ───

async def embeddings(request: Request, db: Session, body: EmbeddingRequest, caller: Caller):
    call = Call(request, caller, "embeddings", body.model)
    target = resolve_model(db, body.model, caller, Capability.EMBEDDING)
    call.model_id = target.model_id
    inputs = [body.input] if isinstance(body.input, str) else list(body.input)
    if not inputs or len(inputs) > 2048 or any(not s for s in inputs):
        raise OpenAIError(400, "invalid_request_error", "input must be a non-empty string or 1 to 2048 non-empty strings.",
                          param="input")
    if body.dimensions and target.embedding_dims and body.dimensions > target.embedding_dims:
        raise OpenAIError(400, "invalid_request_error",
                          f"dimensions must be at most {target.embedding_dims} for this model.", param="dimensions")
    rt = await prepare(call, target)
    try:
        async with manager.client(rt) as client:
            r = await client.post("/embed", json={"input": inputs, "dimensions": body.dimensions})
    except httpx.HTTPError as e:
        raise _worker_error(str(e) or e.__class__.__name__)
    finally:
        manager.release(rt)
    if r.status_code == 400:
        raise OpenAIError(400, "invalid_request_error", r.json().get("error", "Invalid input."))
    if r.status_code != 200:
        raise _worker_error(f"HTTP {r.status_code}")
    out = r.json()
    tokens = int(out["prompt_tokens"])
    call.finish(200, None, tokens, 0)

    def encode(vec):
        if body.encoding_format == "base64":
            return base64.b64encode(struct.pack(f"<{len(vec)}f", *vec)).decode()
        return vec

    return JSONResponse({"object": "list", "model": target.api_name,
                         "data": [{"object": "embedding", "index": i, "embedding": encode(v)} for i, v in enumerate(out["data"])],
                         "usage": {"prompt_tokens": tokens, "total_tokens": tokens}}, headers=_headers(call))


# ─── 決策 ───

def _decision_text(value) -> str:
    """input 可以是字串，或 messages（content 是字串或 input_text 片段）；圖片暫不支援。"""
    if isinstance(value, str):
        return value
    texts = []
    for m in value:
        content = m.get("content") if isinstance(m, dict) else None
        if isinstance(content, str):
            texts.append(content)
            continue
        for part in content or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "input_image":
                raise unsupported("Image input for decisions is not supported yet.", "input")
            if part.get("type") in ("input_text", "text"):
                texts.append(part.get("text", ""))
    text = "\n".join(t for t in texts if t)
    if not text:
        raise OpenAIError(400, "invalid_request_error", "input must contain text.", param="input")
    return text


async def decisions(request: Request, db: Session, body: DecisionRequest, caller: Caller):
    call = Call(request, caller, "decisions", body.model)
    target = resolve_model(db, body.model, caller, Capability.DECISION)
    call.model_id = target.model_id
    text = _decision_text(body.input)
    rt = await prepare(call, target)
    try:
        async with manager.client(rt) as client:
            r = await client.post("/decide", json={"input": text, "questions": [q.model_dump() for q in body.questions]})
    except httpx.HTTPError as e:
        raise _worker_error(str(e) or e.__class__.__name__)
    finally:
        manager.release(rt)
    if r.status_code == 400:
        raise OpenAIError(400, "invalid_request_error", r.json().get("error", "Invalid input."))
    if r.status_code != 200:
        raise _worker_error(f"HTTP {r.status_code}")
    out = r.json()
    tokens = int(out["input_tokens"])
    call.finish(200, None, tokens, 0)
    return JSONResponse({"model": target.api_name, "answers": out["answers"],
                         "usage": {"input_tokens": tokens, "output_tokens": 0, "total_tokens": tokens}},
                        headers=_headers(call))
