"""從 Hugging Face 下載模型檔。Superuser 在後台按「下載」才會執行，載入時不會自動下載。

檔案放在 MODEL_DIR/<repo 名稱>（不用 ~/.cache/huggingface），後台才算得出每個模型佔多少磁碟，刪除時也能清乾淨。
"""
import logging
import shutil
import threading
from pathlib import Path

from models.llm_models import DownloadStatus, LLMModel
from utils.db_conn import get_db_context
from utils.settings import settings

logger = logging.getLogger(__name__)
_running: set[int] = set()


def dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def repo_size(repo: str) -> int | None:
    from huggingface_hub import HfApi

    info = HfApi().model_info(repo, files_metadata=True, token=settings.hf_token)
    return sum(s.size or 0 for s in info.siblings or [])


def _update(model_id: int, **fields) -> None:
    with get_db_context() as db:
        model = db.get(LLMModel, model_id)
        if model:
            for k, v in fields.items():
                setattr(model, k, v)
            db.commit()


def start(model_id: int) -> bool:
    if model_id in _running:
        return False
    _running.add(model_id)
    _update(model_id, download_status=DownloadStatus.DOWNLOADING, download_progress=0, download_error=None)
    threading.Thread(target=_run, args=(model_id,), name=f"download-{model_id}", daemon=True).start()
    return True


def _run(model_id: int) -> None:
    try:
        with get_db_context() as db:
            model = db.get(LLMModel, model_id)
            repo, path, weights_mb = model.source_repo, model.files_path(settings.model_dir), model.est_weights_mb
        settings.model_dir.mkdir(parents=True, exist_ok=True)
        total = repo_size(repo)
        free = shutil.disk_usage(settings.model_dir).free
        if total and total * 1.05 > free:
            raise RuntimeError(f"磁碟空間不夠：需要 {total / 2 ** 30:.1f} GB，只剩 {free / 2 ** 30:.1f} GB")
        _update(model_id, size_bytes=total)

        done = threading.Event()

        def watch() -> None:
            while not done.wait(2):
                if total:
                    _update(model_id, download_progress=min(99, int(dir_size(path) * 100 / total)))

        threading.Thread(target=watch, daemon=True).start()
        from huggingface_hub import snapshot_download
        try:
            snapshot_download(repo_id=repo, local_dir=str(path), token=settings.hf_token)
        finally:
            done.set()
        size = dir_size(path)
        _update(model_id, download_status=DownloadStatus.DOWNLOADED, download_progress=100, size_bytes=size,
                est_weights_mb=weights_mb or round(size / 2 ** 20))
        logger.info("下載完成 %s（%.1f GB）", repo, size / 2 ** 30)
    except Exception as e:  # noqa: BLE001  任何錯誤都要回報到畫面
        logger.exception("下載失敗 %s", model_id)
        _update(model_id, download_status=DownloadStatus.FAILED, download_error=str(e)[:1000])
    finally:
        _running.discard(model_id)


def delete_files(model: LLMModel) -> bool:
    """只刪 MODEL_DIR 底下的資料夾；自訂 local_path 的模型不動檔案。"""
    path = model.files_path(settings.model_dir).resolve()
    root = settings.model_dir.resolve()
    if root not in path.parents or not path.exists():
        return False
    shutil.rmtree(path)
    return True
