"""後台 /api 的請求格式。"""
from datetime import date

from pydantic import BaseModel, Field

from models.llm_models import Capability, Engine


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class ProfileUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    model_ids: list[int] | None = None        # None：可用會員的全部模型
    rpm_limit: int | None = Field(None, ge=1)  # None：等於會員上限
    expires_on: date | None = None


class MemberCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    note: str | None = None
    monthly_token_quota: int = Field(0, ge=0)
    rpm_limit: int = Field(60, ge=1, le=10000)
    max_keys: int = Field(10, ge=1, le=50)
    model_ids: list[int] = []


class MemberUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    email: str | None = None
    note: str | None = None
    is_active: bool | None = None
    monthly_token_quota: int | None = Field(None, ge=0)
    rpm_limit: int | None = Field(None, ge=1, le=10000)
    max_keys: int | None = Field(None, ge=1, le=50)
    model_ids: list[int] | None = None


class AdminCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str
    is_superuser: bool = False


class AdminUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    is_superuser: bool | None = None
    is_active: bool | None = None


class ModelCreate(BaseModel):
    source_repo: str = Field(min_length=3, max_length=300, pattern=r"^[\w.\-]+/[\w.\-]+$")
    api_name: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9.\-_]*$")
    display_name: str | None = None
    engine: str | None = None                  # None：依能力判斷
    capabilities: list[str] = Field(min_length=1)
    context_length: int = Field(32768, ge=512)
    embedding_dims: int | None = Field(None, ge=1)
    est_kv_mb: int = Field(800, ge=0)
    start_download: bool = True

    def resolved_engine(self) -> str:
        if self.engine:
            return self.engine
        if Capability.EMBEDDING in self.capabilities:
            return Engine.MLX_EMBEDDINGS
        return Engine.MLX_VLM if Capability.VISION in self.capabilities else Engine.MLX_LM


class ModelUpdate(BaseModel):
    display_name: str | None = None
    capabilities: list[str] | None = None
    aliases: list[str] | None = None
    context_length: int | None = Field(None, ge=512)
    default_max_tokens: int | None = Field(None, ge=0)
    concurrency: int | None = Field(None, ge=1, le=8)
    queue_max: int | None = Field(None, ge=0, le=256)
    est_weights_mb: int | None = Field(None, ge=0)
    est_kv_mb: int | None = Field(None, ge=0)
    embedding_dims: int | None = Field(None, ge=1)
    is_enabled: bool | None = None
    note: str | None = None
