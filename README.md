<h1 align="center"><img src="docs/assets/logo-wordmark.png" alt="LLMPort" width="420" /></h1>

在 Mac mini 上用 [MLX](https://github.com/ml-explore/mlx) 部署本地模型，對外提供 **OpenAI 相容的 API**，並附一個後台管理模型、會員、API Key 與用量。外網經 Cloudflare Tunnel 連進來，機器不用開任何對外 port。

- **OpenAI 相容**：`/v1/chat/completions`（可串流、可帶圖片）、`/v1/embeddings`、`/v1/decisions`（Jev／OpenAI Decisions 類型）、`/v1/models`。現有的 OpenAI SDK 只要改 `base_url` 和 `api_key`。
- **模型管理（只給管理者）**：一個模型一個 worker 行程，載入就是啟動行程，卸載就是結束行程。只手動載入，載入前會先檢查記憶體放不放得下。
- **會員自己管金鑰**：管理者建立會員帳號、設上限（每月 token、最多幾把金鑰；不限制每分鐘請求數）；每個帳號都能用系統上全部啟用中的模型；會員登入後自己建立、撤銷 API Key，看自己的用量。
- **監控與統計**：統一記憶體組成、記憶體壓力、每個 worker 的狀態與速度、每日 token 用量、請求紀錄。

> 雛形與設計討論：見 [docs/design.md](docs/design.md)。

## 架構

```
API 用戶端 ──HTTPS──▶ Cloudflare（api.example.com，只轉送 /v1/*）─┐
瀏覽器 ─────HTTPS──▶ Cloudflare（console.example.com）────────────┤  同一條 tunnel（由本機主動連出）
                                                                    ▼
Mac mini（macOS 原生執行）  cloudflared ──▶ FastAPI :8080 ──串流──▶ 模型 worker（每個模型一個子行程，127.0.0.1:9100+id）
                                              │                       mlx-lm／mlx-vlm／mlx-embeddings
                                              ├──▶ PostgreSQL（會員、金鑰、模型登記、用量、操作紀錄）
                                              └──▶ Redis（本月 token 計數）
```

MLX 需要 Apple GPU（Metal），Docker 容器跑在 Linux 虛擬機裡用不到，所以 **FastAPI 和模型 worker 必須在 macOS 原生執行**；PostgreSQL 與 Redis 放在 Docker（`docker-compose.yml`）。

一個 `/v1` 請求依序經過：驗證金鑰（401）→ 會員與金鑰狀態（403）→ 解析模型與權限（404）→ 本月配額（429）→ 模型已載入？（503 `model_not_loaded`）→ 排隊（503 `model_busy`）→ 轉給 worker（502）→ 記錄用量。錯誤一律照 OpenAI 的格式回傳。

## 本機開發

需要 Python 3.12、Poetry、Node.js 20 以上、Docker。

```bash
cp .env.example .env            # 至少改 POSTGRES_PASSWORD；本機開發保留 FAKE_WORKERS=true
docker compose up -d            # PostgreSQL（5433）與 Redis（6380）
poetry install
poetry run alembic upgrade head
poetry run python create_superuser.py
poetry run python seed_models.py          # 登記預設的三個模型（不會下載）
cd templates && npm install && npm run build && cd ..
poetry run python main.py                 # http://127.0.0.1:8080
```

前端開發用 `cd templates && npm run dev`（http://localhost:5173，`/api` 與 `/v1` 代理到 8080）。

**沒有模型檔也能跑**：`FAKE_WORKERS=true` 時，還沒下載的模型會用「假 worker」載入。它一樣是真的子行程、一樣經過記憶體檢查與排隊，只是回覆、向量與決策機率是模擬的，方便開發與展示整條流程。正式環境設成 `false`。

## 在 Mac mini 上部署

1. 照上面的步驟裝好，`.env` 設 `FAKE_WORKERS=false`、`MODEL_DIR`（例如 `~/LLMPort/models`），再安裝 MLX：`poetry install --with mlx`。
2. 下載模型：用 Superuser 登入後台，在「模型」頁按「從 Hugging Face 下載」。需要授權的模型（Gemma、Llama 等）要在 `.env` 設 `HF_TOKEN`。也可以自己放到 `MODEL_DIR` 後執行 `poetry run python seed_models.py --mark-downloaded`。載入時不會自動下載。
3. 讓 GPU 能用更多記憶體（選用）：`deploy/launchd/com.llmport.wired-limit.plist` 每次開機套用 `iogpu.wired_limit_mb`，數字要跟後台「系統設定 → Metal 上限」一致。
4. 開機自動啟動：`deploy/launchd/com.llmport.api.plist`（說明在檔案開頭）。只能跑一個 FastAPI 行程，模型 worker 的狀態放在它的記憶體裡。
5. 不睡眠、停電後自動開機：`sudo pmset -a sleep 0 autorestart 1`。
6. Cloudflare Tunnel：照 `deploy/cloudflared/config.yml.example` 設定兩個網域，`.env` 設 `API_HOST`、`CONSOLE_HOST`、`CLOUDFLARED_METRICS_URL`。

> MLX 引擎（`workers/engines/mlx_engines.py`）是依 mlx-lm、mlx-vlm、mlx-embeddings 的公開 API 撰寫，**還沒有用真的模型跑過**。第一次在 Mac mini 載入時請留意後台的 worker log（`tmp_files/logs/worker-*.log`）。

## 呼叫 API

會員登入後台，在「金鑰管理」建立金鑰（完整金鑰只顯示一次），「請求測試」頁有對應的 Python 與 curl 範例。

```python
from openai import OpenAI

client = OpenAI(base_url="https://api.example.com/v1", api_key="sk-lp-...")
resp = client.chat.completions.create(model="qwen3-4b", messages=[{"role": "user", "content": "你好"}])
print(resp.choices[0].message.content, resp.usage)
```

決策 API（不產生文字，回每個問題的機率）：

```bash
curl https://api.example.com/v1/decisions \
  -H "Authorization: Bearer $LLMPORT_KEY" -H "Content-Type: application/json" \
  -d '{"model": "qwen3-4b", "input": "訂單扣款了還沒出貨，請退款",
       "questions": [{"type": "predicate", "name": "refund", "instructions": "是否要求退款"},
                     {"type": "choice", "name": "dept", "instructions": "部門",
                      "choices": [{"value": "billing"}, {"value": "shipping"}]}]}'
```

| HTTP | code | 什麼時候 |
|------|------|----------|
| 401 | `invalid_api_key` | 金鑰錯誤或已撤銷 |
| 403 | `key_disabled` | 帳號停用或金鑰過期 |
| 404 | `model_not_found` | 模型不存在或已停用 |
| 400 | `unsupported_capability` | 例如對不支援視覺的模型傳圖片 |
| 429 | `insufficient_quota` | 本月 token 用完 |
| 503 | `model_not_loaded`／`model_busy` | 模型沒載入（只能由管理者手動載入）／佇列滿了 |
| 502 | `worker_error` | worker 執行失敗 |

第一版還不支援 tools（function calling）與 `response_format` 的 JSON Schema；決策 API 每題最多 26 個選項，暫不支援圖片輸入。

## 角色

| 功能 | Superuser | 管理員 | 會員 |
|------|:--:|:--:|:--:|
| 總覽、系統監控、所有人的用量與請求紀錄 | ✓ | ✓ | |
| 載入、卸載模型 | ✓ | ✓ | |
| 新增、刪除、下載模型，修改模型設定 | ✓ | | |
| 帳號管理：會員（建立、上限、重設密碼、停用、撤銷金鑰） | ✓ | ✓ | |
| 帳號管理：管理者帳號、操作紀錄；系統設定 | ✓ | | |
| 自己的 API Key、用量、請求紀錄（服務中心） | ✓ | ✓ | ✓ |
| 請求測試 | ✓ | ✓ | ✓ |

側欄分兩組：**服務中心**（總覽〔系統可用模型、本月用量趨勢〕、金鑰管理〔點金鑰看它的用量統計〕、請求紀錄、請求測試）人人都有；**管理中心**（模型管理、帳號管理、用量統計〔全部帳號〕、系統監控）只給管理者；系統設定在系統監控右上角（只有 Superuser）。每個帳號的金鑰都能用全部啟用中的模型（沒載入的回 503）。帳號設定（名稱、密碼）與登出在左下角的使用者選單。

會員帳號由管理者建立並產生初始密碼，第一次登入必須修改，不開放自行註冊。

## 專案結構

```
main.py              FastAPI 入口：/v1、/api、後台頁面
create_superuser.py  建立第一位 Superuser
seed_models.py       登記預設模型
models/  schemas/    SQLAlchemy 2.0 資料表、Pydantic 請求格式
routers/             auth、me（會員自己的）、members、admins、models_admin、usage、system、v1（含測試台）
services/            gateway（/v1 閘道）、model_manager（啟停 worker、記憶體檢查）、limits、usage、
                     monitor、metrics、downloads、accounts、catalog、system_settings、audit
workers/             server.py（worker 行程）、decision.py（決策計分）、engines/（fake、mlx_engines）
utils/               settings、db_conn、redis_conn、auth、api_key、openai_errors
alembic/             資料庫 migration
templates/           Vue 3 後台（Vite、Pinia、vue-router）
tests/               pytest：SQLite、fakeredis、假 worker，不載入真模型
deploy/              launchd 與 cloudflared 範本
```

## 測試

```bash
poetry run pytest -q
```

測試不會載入真的模型、也不會連外網；其中一個測試會真的啟動假 worker 子行程，走完載入 → 呼叫 → 卸載。

## 授權

[MIT](LICENSE)
