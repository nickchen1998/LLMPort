from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from . import Base, JSONType


class AuditLog(Base):
    """後台操作紀錄：載入卸載模型、建立撤銷金鑰、改會員上限、改設定…。"""
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    actor_label = Column(String(254), nullable=False)
    action = Column(String(60), nullable=False)
    target = Column(String(300), nullable=True)
    detail = Column(JSONType, nullable=True)
