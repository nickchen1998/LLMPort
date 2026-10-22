from datetime import datetime

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from . import Base


class Source:
    API = "api"
    PLAYGROUND = "playground"


class RequestLog(Base):
    """每個 /v1 請求一筆（含失敗），預設不保存提示詞與回應內容。"""
    __tablename__ = "request_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    request_id = Column(String(40), nullable=False)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True, index=True)
    api_key_id = Column(Integer, ForeignKey("api_key.id", ondelete="SET NULL"), nullable=True)
    model_id = Column(Integer, ForeignKey("llm_model.id", ondelete="SET NULL"), nullable=True)
    model_name = Column(String(100), nullable=True)          # 用戶端送來的 model 欄位
    endpoint = Column(String(40), nullable=False)
    status_code = Column(Integer, nullable=False)
    error_code = Column(String(40), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    ttft_ms = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=False, default=0)
    stream = Column(Boolean, nullable=False, default=False)
    has_image = Column(Boolean, nullable=False, default=False)
    source = Column(String(20), nullable=False, default=Source.API)
    client_country = Column(String(8), nullable=True)        # Cloudflare 的 CF-IPCountry
    user_agent = Column(String(300), nullable=True)

    __table_args__ = (Index("ix_request_log_user_created", "user_id", "created_at"),)


class UsageDaily(Base):
    """每日彙總（日期 × 會員 × 金鑰 × 模型），永久保留。api_key_id 為 0 表示測試台。"""
    __tablename__ = "usage_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    user_id = Column(Integer, nullable=False)
    api_key_id = Column(Integer, nullable=False, default=0)
    model_id = Column(Integer, nullable=False, default=0)
    requests = Column(Integer, nullable=False, default=0)
    errors = Column(Integer, nullable=False, default=0)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("date", "user_id", "api_key_id", "model_id", name="uq_usage_daily"),
        Index("ix_usage_daily_user_date", "user_id", "date"),
    )
