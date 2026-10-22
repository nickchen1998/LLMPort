from datetime import datetime
from pathlib import Path

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String, Text

from . import Base, JSONType


class Engine:
    MLX_LM = "mlx-lm"                  # 文字對話、決策
    MLX_VLM = "mlx-vlm"                # 對話＋看圖
    MLX_EMBEDDINGS = "mlx-embeddings"  # 嵌入
    ALL = (MLX_LM, MLX_VLM, MLX_EMBEDDINGS)


class Capability:
    CHAT = "chat"
    VISION = "vision"
    EMBEDDING = "embedding"
    DECISION = "decision"
    ALL = (CHAT, VISION, EMBEDDING, DECISION)


class DownloadStatus:
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class LLMModel(Base):
    """登記的模型。執行狀態（是否載入、PID、記憶體）不進資料庫，放在 services.model_manager。"""
    __tablename__ = "llm_model"

    id = Column(Integer, primary_key=True, autoincrement=True)
    api_name = Column(String(100), nullable=False, unique=True)   # 呼叫時 model 欄位填這個
    display_name = Column(String(200), nullable=False)
    source_repo = Column(String(300), nullable=False)              # Hugging Face repo，例 mlx-community/Qwen3-4B-Instruct-2507-4bit
    local_path = Column(String(500), nullable=True)                # 空值時放在 MODEL_DIR/<repo 名稱>
    engine = Column(String(30), nullable=False)
    capabilities = Column(JSONType, nullable=False, default=list)
    quant = Column(String(20), nullable=True)
    est_weights_mb = Column(Integer, nullable=False, default=0)
    est_kv_mb = Column(Integer, nullable=False, default=0)
    context_length = Column(Integer, nullable=False, default=32768)
    default_max_tokens = Column(Integer, nullable=False, default=1024)
    embedding_dims = Column(Integer, nullable=True)
    concurrency = Column(Integer, nullable=False, default=1)
    queue_max = Column(Integer, nullable=False, default=8)
    aliases = Column(JSONType, nullable=False, default=list)
    is_enabled = Column(Boolean, nullable=False, default=True)
    download_status = Column(String(20), nullable=False, default=DownloadStatus.NOT_DOWNLOADED)
    download_error = Column(Text, nullable=True)
    download_progress = Column(Integer, nullable=False, default=0)    # 0–100
    size_bytes = Column(BigInteger, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    @property
    def est_mb(self) -> int:
        return (self.est_weights_mb or 0) + (self.est_kv_mb or 0)

    def has(self, capability: str) -> bool:
        return capability in (self.capabilities or [])

    def files_path(self, model_dir: Path) -> Path:
        if self.local_path:
            return Path(self.local_path).expanduser()
        return model_dir / self.source_repo.split("/")[-1]
