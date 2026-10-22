"""測試共用 fixtures：in-memory SQLite、fakeredis、ASGI 直接接上的假 worker，不載入真模型、不連外網。"""
import os

os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["SECRET_KEY"] = "test-secret-key-for-pytest-only"
os.environ["FAKE_WORKERS"] = "true"
os.environ["FAKE_TPS"] = "0"
os.environ["FAKE_LOAD_SECONDS"] = "0"
os.environ.pop("API_HOST", None)

import fakeredis  # noqa: E402
import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

import main  # noqa: E402
from models import Base  # noqa: E402
from models.llm_models import LLMModel  # noqa: E402
from models.users import User  # noqa: E402
from services import gateway  # noqa: E402
from services.catalog import DEFAULT_MODELS  # noqa: E402
from services.model_manager import manager  # noqa: E402
from utils import db_conn, redis_conn  # noqa: E402
from utils.auth import create_access_token, hash_password  # noqa: E402
from workers.engines.fake import FakeEngine  # noqa: E402
from workers.server import create_app  # noqa: E402

PASSWORD = "Test-Password-1234!"


@pytest.fixture()
def SessionLocal(tmp_path):
    # 用檔案而不是 in-memory：in-memory 要共用一條連線，請求結束時的 rollback 會把背景執行緒剛寫的用量一起還原
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False, "timeout": 10},
                           poolclass=NullPool)
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db_conn.set_session_factory(factory)
    yield factory
    db_conn.set_session_factory(None)
    engine.dispose()


@pytest.fixture()
def db(SessionLocal):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    redis_conn.set_redis(client)
    yield client
    redis_conn.set_redis(None)


@pytest.fixture(autouse=True)
def clean_manager():
    manager.runtimes.clear()
    yield
    manager.runtimes.clear()


@pytest.fixture()
async def client(SessionLocal):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://testserver") as c:
        yield c
    await gateway.drain()


def make_user(db, email: str, role: str = "member", **kw) -> User:
    user = User(email=email, name=kw.pop("name", email.split("@")[0]), hashed_password=hash_password(PASSWORD),
                is_superuser=role == "superuser", is_staff=role in ("superuser", "admin"), **kw)
    db.add(user)
    db.commit()
    return user


def auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.fixture()
def models(db) -> dict[str, LLMModel]:
    out = {}
    for spec in DEFAULT_MODELS:
        model = LLMModel(**spec)
        db.add(model)
        out[spec["api_name"]] = model
    db.commit()
    return out


def attach(model: LLMModel):
    """把模型接上 ASGI 的假 worker（狀態直接是已載入）。"""
    app = create_app(lambda: FakeEngine("", name=model.api_name, dims=model.embedding_dims, simulated_mb=model.est_mb),
                     eager=True)
    return manager.attach_test_worker(model, httpx.ASGITransport(app=app), mem_mb=model.est_mb)


@pytest.fixture()
def superuser(db):
    return make_user(db, "owner@example.com", "superuser")


@pytest.fixture()
def admin(db):
    return make_user(db, "ops@example.com", "admin")


@pytest.fixture()
def member(db, models):
    return make_user(db, "an@example.com", max_keys=3)


@pytest.fixture()
async def member_key(client, member) -> str:
    r = await client.post("/api/me/keys", json={"name": "測試"}, headers=auth(member))
    assert r.status_code == 201, r.text
    return r.json()["key"]


def bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}
