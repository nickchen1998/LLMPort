"""登記預設的三個模型（不會下載）。已經登記過的 API 名稱會略過。

    poetry run python seed_models.py

要下載模型檔，在後台「模型」頁按「下載」（Superuser），或手動放到 MODEL_DIR 後執行
    poetry run python seed_models.py --mark-downloaded
把資料夾已存在的模型標成已下載。
"""
import argparse

from models import import_all_models
from models.llm_models import DownloadStatus, LLMModel
from services.catalog import DEFAULT_MODELS
from utils.db_conn import get_db_context
from utils.settings import settings

import_all_models()


def main() -> None:
    parser = argparse.ArgumentParser(description="登記預設模型")
    parser.add_argument("--mark-downloaded", action="store_true", help="MODEL_DIR 裡已有資料夾的模型標成已下載")
    args = parser.parse_args()
    with get_db_context() as db:
        for spec in DEFAULT_MODELS:
            if db.query(LLMModel).filter(LLMModel.api_name == spec["api_name"]).first():
                print(f"略過 {spec['api_name']}（已登記）")
                continue
            db.add(LLMModel(**spec))
            print(f"登記 {spec['api_name']} ← {spec['source_repo']}")
        db.commit()
        if args.mark_downloaded:
            for model in db.query(LLMModel).all():
                if model.files_path(settings.model_dir).exists():
                    model.download_status, model.download_progress = DownloadStatus.DOWNLOADED, 100
                    print(f"{model.api_name}：找到模型檔，標成已下載")
            db.commit()


if __name__ == "__main__":
    main()
