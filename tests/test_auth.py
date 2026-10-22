from tests.conftest import PASSWORD, auth, make_user


async def login(client, email, password=PASSWORD):
    return await client.post("/api/auth/login", data={"username": email, "password": password})


async def test_login_returns_token_and_role(client, member):
    r = await login(client, "AN@example.com")
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["role"] == "member"
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.json()["email"] == "an@example.com"


async def test_wrong_password_then_lockout(client, member):
    for _ in range(5):
        assert (await login(client, member.email, "wrong")).status_code == 401
    r = await login(client, member.email)
    assert r.status_code == 429
    assert "分鐘後再試" in r.json()["detail"]


async def test_disabled_account_cannot_login(client, db, member):
    member.is_active = False
    db.commit()
    assert (await login(client, member.email)).status_code == 403


async def test_change_password_rules(client, member):
    h = auth(member)
    r = await client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "short"}, headers=h)
    assert r.status_code == 400 and "至少 16 碼" in r.json()["detail"]
    r = await client.post("/api/auth/password", json={"current_password": "nope", "new_password": "Another-Pass-5678!"},
                          headers=h)
    assert r.status_code == 400
    r = await client.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "Another-Pass-5678!"},
                          headers=h)
    assert r.status_code == 200
    assert (await login(client, member.email, "Another-Pass-5678!")).status_code == 200


async def test_role_guards(client, db, member, admin, superuser):
    assert (await client.get("/api/members", headers=auth(member))).status_code == 403
    assert (await client.get("/api/models", headers=auth(member))).status_code == 403
    assert (await client.get("/api/members", headers=auth(admin))).status_code == 200
    assert (await client.get("/api/settings", headers=auth(admin))).status_code == 403
    assert (await client.get("/api/admins", headers=auth(admin))).status_code == 403
    assert (await client.get("/api/settings", headers=auth(superuser))).status_code == 200
    # 管理者沒有自己的 API Key
    assert (await client.post("/api/me/keys", json={"name": "x"}, headers=auth(admin))).status_code == 403
    assert (await client.get("/api/me/summary")).status_code == 401


async def test_last_superuser_cannot_be_demoted(client, db, superuser):
    r = await client.patch(f"/api/admins/{superuser.id}", json={"is_superuser": False}, headers=auth(superuser))
    assert r.status_code == 400 and "至少要保留" in r.json()["detail"]
    other = make_user(db, "second@example.com", "superuser")
    r = await client.patch(f"/api/admins/{other.id}", json={"is_superuser": False}, headers=auth(superuser))
    assert r.status_code == 200 and r.json()["role"] == "admin"
