from datetime import date, timedelta

from models.users import ApiKey
from tests.conftest import auth, bearer
from tests.test_auth import login


async def test_member_creates_key_shown_once(client, db, member):
    r = await client.post("/api/me/keys", json={"name": "Open WebUI"}, headers=auth(member))
    assert r.status_code == 201
    body = r.json()
    assert body["key"].startswith("sk-lp-") and len(body["key"]) == 46
    assert body["masked"].startswith("sk-lp-") and body["masked"].endswith(body["key"][-4:])
    stored = db.query(ApiKey).one()
    assert body["key"] not in (stored.hashed_key, stored.key_prefix)
    listed = (await client.get("/api/me/keys", headers=auth(member))).json()
    assert "key" not in listed[0]


async def test_key_limits(client, member, models):
    h = auth(member)
    r = await client.post("/api/me/keys", json={"name": "過期", "expires_on": date.today().isoformat()}, headers=h)
    assert r.status_code == 400
    for i in range(3):
        assert (await client.post("/api/me/keys", json={"name": f"k{i}"}, headers=h)).status_code == 201
    r = await client.post("/api/me/keys", json={"name": "第四把"}, headers=h)
    assert r.status_code == 400 and "最多 3 把" in r.json()["detail"]


async def test_member_revokes_own_key_but_not_others(client, db, member, member_key):
    from tests.conftest import make_user

    other = make_user(db, "kai@example.com")
    key_id = db.query(ApiKey).one().id
    assert (await client.delete(f"/api/me/keys/{key_id}", headers=auth(other))).status_code == 404
    assert (await client.delete(f"/api/me/keys/{key_id}", headers=auth(member))).status_code == 200
    r = await client.get("/v1/models", headers=bearer(member_key))
    assert r.status_code == 401 and r.json()["error"]["code"] == "invalid_api_key"


async def test_admin_creates_member_with_initial_password(client, admin, models):
    r = await client.post("/api/members", json={"name": "星野工作室", "email": "Hoshino@Example.com",
                                                "monthly_token_quota": 7500000, "max_keys": 3}, headers=auth(admin))
    assert r.status_code == 201
    body = r.json()
    assert body["member"]["email"] == "hoshino@example.com"
    login_r = await login(client, "hoshino@example.com", body["initial_password"])
    assert login_r.status_code == 200 and login_r.json()["user"]["must_change_password"] is True
    dup = await client.post("/api/members", json={"name": "x", "email": "hoshino@example.com"}, headers=auth(admin))
    assert dup.status_code == 400


async def test_admin_sees_keys_without_full_key_and_can_revoke(client, db, admin, member, member_key):
    keys = (await client.get(f"/api/members/{member.id}/keys", headers=auth(admin))).json()
    assert len(keys) == 1 and "key" not in keys[0] and member_key not in str(keys)
    r = await client.delete(f"/api/keys/{keys[0]['id']}", headers=auth(admin))
    assert r.status_code == 200 and r.json()["revoked_at"]


async def test_reset_password_and_disable_member(client, db, admin, member, member_key):
    r = await client.post(f"/api/members/{member.id}/reset-password", headers=auth(admin))
    assert (await login(client, member.email, r.json()["password"])).status_code == 200
    r = await client.patch(f"/api/members/{member.id}", json={"is_active": False}, headers=auth(admin))
    assert r.status_code == 200
    r = await client.get("/v1/models", headers=bearer(member_key))
    assert r.status_code == 403 and r.json()["error"]["code"] == "key_disabled"


async def test_expired_key_is_rejected(client, db, member, member_key):
    key = db.query(ApiKey).one()
    key.expires_at = key.created_at - timedelta(days=1)
    db.commit()
    r = await client.get("/v1/models", headers=bearer(member_key))
    assert r.status_code == 403 and "expired" in r.json()["error"]["message"]


async def test_admin_key_can_use_every_enabled_model(client, db, admin, models):
    from tests.conftest import attach

    attach(models["qwen3-4b"])
    r = await client.post("/api/me/keys", json={"name": "我的系統"}, headers=auth(admin))
    assert r.status_code == 201
    data = (await client.get("/v1/models", headers=bearer(r.json()["key"]))).json()["data"]
    assert {m["id"] for m in data} == set(models)
    r = await client.post("/v1/chat/completions", headers=bearer(r.json()["key"]),
                          json={"model": "qwen3-4b", "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
