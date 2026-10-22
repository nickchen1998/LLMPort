from datetime import datetime

from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from . import Base


class Role:
    SUPERUSER = "superuser"   # 所有管理功能，含後台帳號與系統設定
    ADMIN = "admin"           # 管模型載入、會員帳號、撤銷金鑰、看監控
    MEMBER = "member"         # 只看得到自己的金鑰、用量與紀錄


class User(Base):
    """管理者與會員共用一張表：is_superuser／is_staff 決定角色，兩個都是 False 就是會員。"""
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(254), nullable=False, unique=True)
    name = Column(String(100), nullable=False)
    note = Column(Text, nullable=True)                       # 只有管理者看得到
    hashed_password = Column(String(255), nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    is_staff = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    must_change_password = Column(Boolean, default=False, nullable=False)

    monthly_token_quota = Column(BigInteger, default=0, nullable=False)   # 0 表示不限，所有金鑰合計
    max_keys = Column(Integer, default=10, nullable=False)

    last_login_at = Column(DateTime, nullable=True)
    failed_logins = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    api_keys = relationship("ApiKey", back_populates="user", foreign_keys="ApiKey.user_id",
                            cascade="all, delete-orphan", order_by="ApiKey.id.desc()")

    @property
    def role(self) -> str:
        if self.is_superuser:
            return Role.SUPERUSER
        return Role.ADMIN if self.is_staff else Role.MEMBER

    @property
    def is_admin(self) -> bool:
        return self.is_superuser or self.is_staff


class ApiKey(Base):
    """會員自己建立的金鑰。"""
    __tablename__ = "api_key"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    key_prefix = Column(String(20), nullable=False)
    key_last4 = Column(String(8), nullable=False)
    hashed_key = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    revoked_by = Column(Integer, ForeignKey("user.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    user = relationship("User", back_populates="api_keys", foreign_keys=[user_id])

    @property
    def masked(self) -> str:
        return f"{self.key_prefix}…{self.key_last4}"

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def is_expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and self.expires_at <= (now or datetime.now())

