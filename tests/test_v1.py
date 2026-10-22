import base64
import json
import math
import struct

import pytest

from models.usage import RequestLog, UsageDaily
from services import gateway
from services.model_manager import manager
from tests.conftest import attach, auth, bearer


@pytest.fixture()
def loaded(models):
    """對話與看圖、快速模型已載入；嵌入模型沒載入。"""
    return {name: attach(models[name]) for name in ("qwen3-vl-8b", "qwen3-4b")}


async def test_models_lists_allowed_with_loaded_flag(client, member_key, loaded):
    r = await client.get("/v1/models", headers=bearer(member_key))
    data = {m["id"]: m for m in r.json()["data"]}
    assert set(data) == {"qwen3-vl-8b", "qwen3-4b", "qwen3-embed-0.6b"}
    assert data["qwen3-4b"]["loaded"] is True and data["qwen3-embed-0.6b"]["loaded"] is False


async def test_chat_completion_and_usage_recorded(client, db, member, member_key, loaded):
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "你好"}]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "chat.completion" and body["model"] == "qwen3-4b"
    assert "假 worker" in body["choices"][0]["message"]["content"]
    assert body["usage"]["total_tokens"] == body["usage"]["prompt_tokens"] + body["usage"]["completion_tokens"] > 0
    assert r.headers["x-request-id"].startswith("req_") and r.headers["x-ratelimit-limit-requests"] == "60"
    await gateway.drain()
    log = db.query(RequestLog).one()
    assert (log.status_code, log.endpoint, log.user_id) == (200, "chat/completions", member.id)
    daily = db.query(UsageDaily).one()
    assert daily.requests == 1 and daily.completion_tokens == body["usage"]["completion_tokens"]


async def test_chat_stream_with_usage_chunk(client, member_key, loaded):
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "stream": True, "stream_options": {"include_usage": True},
                                "messages": [{"role": "user", "content": "串流測試"}]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [line[6:] for line in r.text.splitlines() if line.startswith("data: ")]
    assert events[-1] == "[DONE]"
    chunks = [json.loads(e) for e in events[:-1]]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks if c["choices"])
    assert "串流測試" in text
    assert chunks[-2]["choices"][0]["finish_reason"] == "stop"
    assert chunks[-1]["choices"] == [] and chunks[-1]["usage"]["completion_tokens"] > 0
    assert manager.get(loaded["qwen3-4b"].model_id).active == 0


async def test_max_tokens_and_stop(client, member_key, loaded):
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "max_tokens": 3, "messages": [{"role": "user", "content": "hi"}]})
    assert r.json()["choices"][0]["finish_reason"] == "length"
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "stop": ["模擬"], "messages": [{"role": "user", "content": "hi"}]})
    assert "模擬" not in r.json()["choices"][0]["message"]["content"]


async def test_alias_and_vision_capability(client, member_key, loaded):
    image = [{"type": "text", "text": "這是什麼？"}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": image}]})
    assert r.status_code == 200 and r.json()["model"] == "qwen3-vl-8b"
    assert "圖片" in r.json()["choices"][0]["message"]["content"]
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": image}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_capability"


async def test_unsupported_parameters(client, member_key, loaded):
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "tools": [{"type": "function"}], "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 400 and r.json()["error"]["param"] == "tools"
    r = await client.post("/v1/chat/completions", headers=bearer(member_key), json={"model": "qwen3-4b", "messages": []})
    assert r.status_code == 400 and r.json()["error"]["type"] == "invalid_request_error"


async def test_embeddings(client, models, member_key):
    attach(models["qwen3-embed-0.6b"])
    r = await client.post("/v1/embeddings", headers=bearer(member_key),
                          json={"model": "qwen3-embed-0.6b", "input": ["第一段", "第二段"]})
    body = r.json()
    assert r.status_code == 200 and len(body["data"]) == 2 and len(body["data"][0]["embedding"]) == 1024
    assert body["usage"]["prompt_tokens"] > 0
    r = await client.post("/v1/embeddings", headers=bearer(member_key),
                          json={"model": "qwen3-embed-0.6b", "input": "縮短", "dimensions": 256, "encoding_format": "base64"})
    raw = base64.b64decode(r.json()["data"][0]["embedding"])
    vec = struct.unpack(f"<{len(raw) // 4}f", raw)
    assert len(vec) == 256 and math.isclose(math.sqrt(sum(x * x for x in vec)), 1, rel_tol=1e-4)
    r = await client.post("/v1/embeddings", headers=bearer(member_key),
                          json={"model": "qwen3-embed-0.6b", "input": "x", "dimensions": 4096})
    assert r.status_code == 400


async def test_decisions(client, member_key, loaded):
    r = await client.post("/v1/decisions", headers=bearer(member_key), json={
        "model": "qwen3-4b",
        "input": "訂單上週就扣款了，到現在還沒出貨，請直接幫我退款！",
        "questions": [
            {"type": "predicate", "name": "wants_refund", "instructions": "使用者是否要求退款"},
            {"type": "choice", "name": "department", "instructions": "這張單應該分給哪個部門",
             "choices": [{"value": "billing", "description": "帳務與退款"}, {"value": "shipping", "description": "物流出貨"}]},
            {"type": "score", "name": "urgency", "instructions": "有多急",
             "levels": [{"label": "低"}, {"label": "中"}, {"label": "高"}]},
        ]})
    assert r.status_code == 200, r.text
    body = r.json()
    pred, choice, score = body["answers"]
    assert pred["type"] == "predicate" and 0 <= pred["probability"] <= 1
    assert choice["choice"] in ("billing", "shipping")
    assert math.isclose(sum(p["probability"] for p in choice["probabilities"]), 1, abs_tol=1e-9)
    assert 0 <= score["score"] <= 2 and [p["value"] for p in score["probabilities"]] == [0, 1, 2]
    assert body["usage"]["output_tokens"] == 0 and body["usage"]["input_tokens"] > 0
    r = await client.post("/v1/decisions", headers=bearer(member_key), json={
        "model": "qwen3-4b", "input": "x", "questions": [{"type": "choice", "instructions": "?", "choices": [{"value": "a"}]}]})
    assert r.status_code == 400
    r = await client.post("/v1/decisions", headers=bearer(member_key), json={
        "model": "qwen3-vl-8b", "input": "x", "questions": [{"type": "predicate", "instructions": "?"}]})
    assert r.status_code == 400 and r.json()["error"]["code"] == "unsupported_capability"


async def test_auth_errors_are_openai_shaped_and_logged(client, db, loaded):
    r = await client.get("/v1/models")
    assert r.status_code == 401 and set(r.json()["error"]) == {"message", "type", "param", "code"}
    r = await client.post("/v1/chat/completions", headers=bearer("sk-lp-wrong"),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "x"}]})
    assert r.json()["error"]["code"] == "invalid_api_key"
    await gateway.drain()
    assert db.query(RequestLog).filter(RequestLog.status_code == 401).count() == 2


async def test_model_not_allowed_is_404(client, db, member, models, loaded):
    r = await client.post("/api/me/keys", json={"name": "只有 4b", "model_ids": [models["qwen3-4b"].id]}, headers=auth(member))
    key = r.json()["key"]
    r = await client.post("/v1/chat/completions", headers=bearer(key),
                          json={"model": "qwen3-vl-8b", "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "model_not_found"


async def test_model_not_loaded_is_503(client, db, member_key, loaded):
    r = await client.post("/v1/embeddings", headers=bearer(member_key), json={"model": "qwen3-embed-0.6b", "input": "x"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_not_loaded"
    await gateway.drain()
    log = db.query(RequestLog).one()
    assert (log.status_code, log.error_code) == (503, "model_not_loaded")


async def test_rate_limit(client, member, loaded):
    r = await client.post("/api/me/keys", json={"name": "慢", "rpm_limit": 2}, headers=auth(member))
    key = r.json()["key"]
    for _ in range(2):
        assert (await client.get("/v1/models", headers=bearer(key))).status_code == 200
    body = {"model": "qwen3-4b", "messages": [{"role": "user", "content": "x"}]}
    assert (await client.post("/v1/chat/completions", headers=bearer(key), json=body)).status_code == 200
    assert (await client.post("/v1/chat/completions", headers=bearer(key), json=body)).status_code == 200
    r = await client.post("/v1/chat/completions", headers=bearer(key), json=body)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limit_exceeded" and r.headers["retry-after"]


async def test_monthly_quota(client, db, member, member_key, loaded):
    member.monthly_token_quota = 10
    db.commit()
    body = {"model": "qwen3-4b", "messages": [{"role": "user", "content": "這一次會用掉超過十個 token"}]}
    assert (await client.post("/v1/chat/completions", headers=bearer(member_key), json=body)).status_code == 200
    await gateway.drain()
    r = await client.post("/v1/chat/completions", headers=bearer(member_key), json=body)
    assert r.status_code == 429 and r.json()["error"]["code"] == "insufficient_quota"


async def test_queue_full_is_model_busy(client, db, models, member_key, loaded):
    rt = manager.get(models["qwen3-4b"].id)
    rt.queue_max = 0
    await manager.acquire(rt)        # 佔住唯一的名額
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "x"}]})
    manager.release(rt)
    assert r.status_code == 503 and r.json()["error"]["code"] == "model_busy"


async def test_playground_uses_login_identity(client, db, member, admin, loaded):
    body = {"model": "qwen3-4b", "messages": [{"role": "user", "content": "測試台"}]}
    assert (await client.post("/api/playground/chat/completions", headers=auth(member), json=body)).status_code == 200
    assert (await client.post("/api/playground/chat/completions", headers=auth(admin), json=body)).status_code == 200
    await gateway.drain()
    rows = db.query(UsageDaily).order_by(UsageDaily.user_id).all()
    assert {(r.user_id, r.api_key_id) for r in rows} == {(member.id, 0), (admin.id, 0)}
    assert {log.source for log in db.query(RequestLog).all()} == {"playground"}
