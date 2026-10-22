# 設計說明與待確認事項

## 已經決定的事

| 決定 | 做法 |
|------|------|
| 前端 Vue 3、後端 FastAPI，架構比照 PTCFormosAI | routers 保持薄、商業邏輯放 services；SQLAlchemy 2.0 Column 寫法、Alembic、Poetry；後台版面沿用深色側欄、底線分頁、左清單右詳情，不疊彈窗 |
| 模型以 MLX 為主，跑在 Mac mini | FastAPI 與模型 worker 在 macOS 原生執行（Docker 用不到 Metal），PostgreSQL、Redis 放 Docker |
| 對話、視覺、嵌入、決策都要 | 決策照 Jev／OpenAI Decisions 類型，用對話模型的下一個 token 機率實作，不另外載入模型 |
| 只有手動載入與卸載 | 沒載入就回 503 `model_not_loaded`，不自動載入、不自動擠掉別的模型；重開機後自動恢復是選用設定，預設關閉 |
| 模型管理只給管理者 | 會員看不到模型頁 |
| 不限制每個帳號能用哪些模型 | 每個帳號都能用全部啟用中的模型，沒有載入的呼叫時回 503；要讓某個模型暫時不能用就把它停用 |
| 會員登入後自己管理 API Key | 管理者設上限、可以撤銷，看不到完整金鑰；管理者不能替會員建立金鑰 |
| 每個帳號都在服務中心管理自己的金鑰 | 帳號（會員與管理者）統一在管理中心的「帳號管理」 |
| 會員帳號由管理者建立 | 系統產生初始密碼，第一次登入要改；不開放自行註冊，忘記密碼由管理者重設 |
| 外網經 Cloudflare Tunnel | API 與後台分兩個網域、同一條 tunnel；API 網域只轉送 `/v1/*` |

## 記憶體怎麼算

```
可再載入 = min( Metal 上限 − 已載入模型,
                可用記憶體 − 安全餘裕 )
預估需要 = 權重大小 + KV 快取預留（依上下文長度）
```

預估需要超過可再載入就擋下，並建議卸載哪一個模型。Metal 上限是 GPU 能鎖定的記憶體，macOS 預設約實體記憶體的 2/3（36 GB 以上約 3/4），可以用 `sysctl iogpu.wired_limit_mb` 調高；這個值重開機會還原，所以用 launchd 在開機時套用。假 worker 的記憶體是模擬的，計算時會從可用記憶體扣掉，讓開發時的檢查跟正式環境一樣。

示意的三個模型（實際型號還沒定）：

| API 名稱 | 來源 | 用途 | 引擎 | 預估記憶體 |
|----------|------|------|------|-----------:|
| qwen3-vl-8b | mlx-community/Qwen3-VL-8B-Instruct-4bit | 對話、視覺 | mlx-vlm | 約 7.1 GB |
| qwen3-4b | mlx-community/Qwen3-4B-Instruct-2507-4bit | 對話、決策 | mlx-lm | 約 3.1 GB |
| qwen3-embed-0.6b | mlx-community/Qwen3-Embedding-0.6B-8bit | 嵌入（1024 維） | mlx-embeddings | 約 0.9 GB |

## 決策 API 的做法

1. 把 input 和一個問題組成提示，選項編成 A、B、C……，要求模型只回一個代號。
2. 只跑一次 prefill，讀最後位置的 logits，只取選項代號那幾個 token 做 softmax。
3. predicate 取「是」的機率；choice 取各選項機率，confidence 用 1 減正規化熵；score 取各等級機率，score 是等級索引乘機率的總和。
4. 機率四捨五入到小數兩位，誤差補在最大的那一項，讓總和剛好是 1。

機率沒有校準過，門檻要用自己標記過的資料來定。之後可以讓同一個 input 的多個問題共用 prompt cache。

## 待確認事項

1. **三個模型的實際型號**：目前用 Qwen3-VL-8B、Qwen3-4B、Qwen3-Embedding-0.6B 示意。
2. **Mac mini 是 16 GB 還是 24 GB**：16 GB 機型的 Metal 預設上限約 10.7 GB，視覺模型要換成 4B 等級。
3. **Superuser 與管理員的分界**：目前管理員可以載入卸載模型、管會員與撤銷金鑰；新增或刪除模型、改模型設定、後台帳號、系統設定只給 Superuser。
4. **配額怎麼算**：目前每位會員一個每月 token 上限，所有金鑰合計，各種 token 一樣算。
5. **要不要保存提示詞與回應內容**：目前不存。
6. **網域與登入保護**：會員也要登入，所以後台不用只允許單一 email 的 Cloudflare Access；建議後台登入加 Cloudflare 限流，Superuser 之後加兩步驟驗證。
7. **決策 API 要不要同時接受 Jev 的格式**（以名稱為 key 的 dict、`noul` 類型）。
8. **其他 endpoint**：有些工具只支援 `/v1/responses` 或舊版 `/v1/completions`。
9. **會員要不要有到期日**：目前只有金鑰能設到期日。
