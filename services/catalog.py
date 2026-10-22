"""模型登記：預設的三個模型，以及給後台的模型輸出格式。"""
from models.llm_models import Capability, Engine, LLMModel

# 雛形討論時的示意組合；實際型號還沒定（見 README 的待確認事項）
DEFAULT_MODELS = [
    {"api_name": "qwen3-vl-8b", "display_name": "Qwen3-VL 8B Instruct",
     "source_repo": "mlx-community/Qwen3-VL-8B-Instruct-4bit", "engine": Engine.MLX_VLM,
     "capabilities": [Capability.CHAT, Capability.VISION], "quant": "4-bit", "est_weights_mb": 5900,
     "est_kv_mb": 1200, "context_length": 32768, "default_max_tokens": 2048, "queue_max": 8,
     "aliases": ["gpt-4o-mini"], "note": "主力模型：一般對話與看圖"},
    {"api_name": "qwen3-4b", "display_name": "Qwen3 4B Instruct 2507",
     "source_repo": "mlx-community/Qwen3-4B-Instruct-2507-4bit", "engine": Engine.MLX_LM,
     "capabilities": [Capability.CHAT, Capability.DECISION], "quant": "4-bit", "est_weights_mb": 2300,
     "est_kv_mb": 800, "context_length": 32768, "default_max_tokens": 1024, "queue_max": 16, "aliases": [],
     "note": "快速模型：短回覆、分類，以及決策 API 的預設模型"},
    {"api_name": "qwen3-embed-0.6b", "display_name": "Qwen3 Embedding 0.6B",
     "source_repo": "mlx-community/Qwen3-Embedding-0.6B-8bit", "engine": Engine.MLX_EMBEDDINGS,
     "capabilities": [Capability.EMBEDDING], "quant": "8-bit", "est_weights_mb": 700, "est_kv_mb": 200,
     "context_length": 8192, "default_max_tokens": 0, "embedding_dims": 1024, "queue_max": 32, "aliases": [],
     "note": "向量模型：RAG 的文件與查詢，1024 維"},
]


def model_out(model: LLMModel, runtime: dict, check: dict | None = None) -> dict:
    return {
        "id": model.id, "api_name": model.api_name, "display_name": model.display_name, "source_repo": model.source_repo,
        "local_path": model.local_path, "engine": model.engine, "capabilities": list(model.capabilities or []),
        "quant": model.quant, "est_weights_mb": model.est_weights_mb, "est_kv_mb": model.est_kv_mb,
        "est_mb": model.est_mb, "context_length": model.context_length, "default_max_tokens": model.default_max_tokens,
        "embedding_dims": model.embedding_dims, "concurrency": model.concurrency, "queue_max": model.queue_max,
        "aliases": list(model.aliases or []), "is_enabled": model.is_enabled, "download_status": model.download_status,
        "download_error": model.download_error, "download_progress": model.download_progress,
        "size_bytes": model.size_bytes, "note": model.note, "runtime": runtime, "load_check": check,
    }


def public_model_out(model: LLMModel, status: str) -> dict:
    """會員看到的模型資訊：只有名稱、能力與現在能不能用。"""
    return {"id": model.id, "api_name": model.api_name, "display_name": model.display_name,
            "capabilities": list(model.capabilities or []), "embedding_dims": model.embedding_dims,
            "context_length": model.context_length, "available": status == "loaded"}


def enabled_models(db) -> list[LLMModel]:
    """每個帳號都能用全部啟用中的模型（沒有載入的呼叫時回 503）。"""
    return db.query(LLMModel).filter(LLMModel.is_enabled.is_(True)).order_by(LLMModel.id).all()
