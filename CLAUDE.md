# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

LLMPort：在 Mac mini 上用 MLX 部署本地模型，對外提供 OpenAI 相容的 `/v1`，並有一個 Vue 後台管理模型、會員、API Key、用量與監控。架構比照 PTCFormosAI（`/Users/bohan/Projects/統智科技_AI智慧語音客服系統/PTCFormosAI`）：routers 保持薄、邏輯放 services、SQLAlchemy 2.0 Column 寫法、Alembic、Poetry。設計決定與待確認事項在 `docs/design.md`，改功能前先看。

已確認、不要任意更動的決定：
- 只手動載入與卸載模型；沒載入回 503 `model_not_loaded`，不自動載入、不擠掉別的模型（重開機恢復是選用設定，預設關閉）。
- 模型管理只給管理者（Superuser 新增／修改／刪除／下載，管理員可以載入卸載）；會員看不到模型頁。
- 會員登入後自己建立、撤銷 API Key；管理者設上限、可以撤銷，看不到完整金鑰，也不能替會員建立金鑰。
- 會員帳號由管理者建立並產生初始密碼（第一次登入要改），不開放自行註冊。
- 決策 API 照 OpenAI Decisions 格式（questions、answers 是陣列），用對話模型的 token 機率實作。

## Common Commands

```bash
docker compose up -d                       # PostgreSQL :5433、Redis :6380（本機 5432／6379 被其他專案占用）
poetry install                             # 真的跑模型時：poetry install --with mlx
poetry run alembic upgrade head
poetry run alembic revision --autogenerate -m "說明"
poetry run python create_superuser.py
poetry run python seed_models.py           # 登記預設三個模型（不下載）
poetry run python main.py                  # FastAPI :8080（也提供 templates/dist）
poetry run pytest -q
cd templates && npm run dev                # Vite :5173，/api、/v1 代理到 :8080
cd templates && npm run build
```

一律用 `poetry run`；UI 文案、註解、commit message 使用繁體中文；`/v1` 的錯誤訊息用英文（照 OpenAI）。

## Architecture

- `services/model_manager.py`：一個模型一個 worker 子行程（`python -m workers.server`），載入＝啟動、卸載＝結束行程；狀態在 FastAPI 行程記憶體，所以 **uvicorn 只能跑一個行程**。worker 只綁 127.0.0.1，用每次啟動隨機的 `X-Worker-Token` 驗證。載入前 `load_check` 算記憶體：`min(Metal 上限 − 已載入, 可用 − 安全餘裕)`。
- `services/gateway.py`：`/v1` 與測試台共用的流程（金鑰 → 會員狀態 → 模型與權限 → 限流與配額 → 已載入 → 排隊 → worker → 記錄用量）。用量在回應後用背景 task 寫（`gateway.spawn`／`drain`），錯誤經 `main.py` 的 `OpenAIError` 處理器記錄。
- `workers/server.py`：MLX 不保證執行緒安全，載入與推論都排進單一執行緒；`/chat` 回 NDJSON 串流。`workers/engines/fake.py` 是假引擎（`FAKE_WORKERS=true` 且沒有模型檔時使用）；`mlx_engines.py` 還沒用真模型驗證過。
- `services/monitor.py`：每 2 秒取樣（psutil、sysctl、macmon、cloudflared /ready），經 `/api/system/stream` SSE 推給後台。
- 會員自己的資料走 `/api/me/*`，一律用登入者 id 查。
- 前端 `templates/`：Vue 3 `<script setup>`、Pinia、vue-router；樣式在 `src/style.css`（沿用 PTCFormosAI 的晴空 tokens，含深色模式）；側欄與權限在 `src/router/routes.js` 的 `meta.roles`。

## Rules

- 測試不載入真模型、不連外網：SQLite 檔案（不要改回 in-memory，共用連線會讓背景用量寫入被 rollback）、fakeredis、`tests/conftest.attach()` 接 ASGI 假 worker。
- 不要讀取或印出 `.env`。完整金鑰與初始密碼只在建立時回傳一次，資料庫只存雜湊。
- 模型檔放 `MODEL_DIR/<repo 名稱>`；worker 設了 `HF_HUB_OFFLINE=1`，載入時不會下載，下載只在後台按「下載」時進行。
