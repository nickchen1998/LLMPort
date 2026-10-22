import asyncio
import time

from models.llm_models import DownloadStatus
from services.model_manager import manager
from tests.conftest import attach, auth, bearer

GB = 1024


def budget(models_mb=0.0, available_mb=16 * GB, metal_limit_mb=16 * GB, headroom_mb=GB):
    return {"total_mb": 24 * GB, "available_mb": available_mb, "system_mb": 6 * GB, "models_mb": models_mb,
            "metal_limit_mb": metal_limit_mb, "headroom_mb": headroom_mb,
            "can_load_mb": max(0, min(metal_limit_mb - models_mb, available_mb - headroom_mb))}


def test_load_check_blocks_and_suggests_unloading(models):
    small = attach(models["qwen3-4b"])          # 3.1 GB
    attach(models["qwen3-embed-0.6b"])          # 0.9 GB
    vl = models["qwen3-vl-8b"]                  # 需要 7.1 GB
    ok = manager.load_check(vl, budget(models_mb=4 * GB, available_mb=12 * GB, metal_limit_mb=12 * GB))
    assert ok["ok"] and ok["fake"]
    blocked = manager.load_check(vl, budget(models_mb=4 * GB, available_mb=12 * GB, metal_limit_mb=9 * GB))
    assert not blocked["ok"] and not blocked["metal_ok"] and blocked["reason"] == "記憶體不夠"
    assert blocked["suggest"]["api_name"] == small.api_name


def test_memory_budget_ignores_fake_worker_memory(models):
    attach(models["qwen3-4b"])
    host = {"total_mb": 24 * GB, "available_mb": 10 * GB}
    b = manager.memory_budget(host, {"metal_limit_gb": 16, "headroom_gb": 1})
    assert b["models_mb"] == models["qwen3-4b"].est_mb
    assert b["available_mb"] == 10 * GB - models["qwen3-4b"].est_mb
    assert b["system_mb"] == 14 * GB


async def test_load_requires_files_without_fake_workers(client, monkeypatch, admin, models):
    monkeypatch.setenv("FAKE_WORKERS", "false")
    r = await client.post(f"/api/models/{models['qwen3-4b'].id}/load", headers=auth(admin))
    assert r.status_code == 400 and "還沒下載" in r.json()["detail"]


async def test_member_cannot_manage_models(client, member, models):
    assert (await client.post(f"/api/models/{models['qwen3-4b'].id}/load", headers=auth(member))).status_code == 403
    summary = (await client.get("/api/me/summary", headers=auth(member))).json()
    assert {m["api_name"] for m in summary["models"]} == {"qwen3-vl-8b", "qwen3-4b", "qwen3-embed-0.6b"}
    assert "runtime" not in summary["models"][0] and summary["models"][0]["available"] is False


async def test_admin_can_load_but_only_superuser_registers(client, admin, superuser):
    body = {"source_repo": "mlx-community/gemma-3-4b-it-qat-4bit", "api_name": "gemma3-4b",
            "capabilities": ["chat", "vision"], "start_download": False}
    assert (await client.post("/api/models", json=body, headers=auth(admin))).status_code == 403
    r = await client.post("/api/models", json=body, headers=auth(superuser))
    assert r.status_code == 201 and r.json()["engine"] == "mlx-vlm" and r.json()["quant"] == "4-bit"
    assert r.json()["download_status"] == DownloadStatus.NOT_DOWNLOADED


async def test_alias_clash_rejected(client, superuser, models):
    r = await client.patch(f"/api/models/{models['qwen3-4b'].id}", json={"aliases": ["gpt-4o-mini"]}, headers=auth(superuser))
    assert r.status_code == 400 and "別名" in r.json()["detail"]


async def test_real_fake_worker_subprocess(client, monkeypatch, admin, member, member_key, models):
    """真的啟動子行程（假引擎），走完載入 → 呼叫 → 卸載。"""
    monkeypatch.setenv("WORKER_PORT_BASE", "19300")
    try:
        await _load_call_unload(client, admin, member_key, models["qwen3-4b"])
    finally:
        await manager.shutdown()


async def _load_call_unload(client, admin, member_key, model):
    r = await client.post(f"/api/models/{model.id}/load", headers=auth(admin))
    assert r.status_code == 200 and r.json()["status"] == "loading"
    deadline = time.monotonic() + 30
    while manager.get(model.id).status == "loading" and time.monotonic() < deadline:
        await asyncio.sleep(.2)
    rt = manager.get(model.id)
    assert rt.status == "loaded", rt.error
    assert rt.pid and rt.mem_mb > 0
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "子行程"}]})
    assert r.status_code == 200 and "子行程" in r.json()["choices"][0]["message"]["content"]
    proc = rt.proc
    r = await client.post(f"/api/models/{model.id}/unload", headers=auth(admin))
    assert r.status_code == 200
    deadline = time.monotonic() + 15
    while manager.get(model.id).status != "unloaded" and time.monotonic() < deadline:
        await asyncio.sleep(.2)
    assert manager.get(model.id).status == "unloaded" and proc.returncode is not None
    r = await client.post("/v1/chat/completions", headers=bearer(member_key),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 503
