from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from . import Base, JSONType


class SystemSetting(Base):
    """後台可以修改的系統設定，預設值見 services/system_settings.DEFAULTS。"""
    __tablename__ = "system_setting"

    key = Column(String(60), primary_key=True)
    value = Column(JSONType, nullable=True)
    updated_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
