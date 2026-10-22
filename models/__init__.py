"""SQLAlchemy 2.0 ORM 模型（比照 PTCFormosAI：declarative_base + Column 寫法）。

JSONType 在 PostgreSQL 使用 JSONB、其他方言（測試用的 SQLite）使用 JSON。
"""
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base

Base = declarative_base()

JSONType = JSON().with_variant(JSONB(), "postgresql")


def import_all_models() -> None:
    """匯入所有模型模組，讓 relationship 與 metadata 完整註冊。"""
    from models import audit, llm_models, system, usage, users  # noqa: F401
