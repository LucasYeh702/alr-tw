# Storage and Purge

ALR-TW v0.6.0 使用單一 managed SQLite store（受管理 SQLite 儲存）保存短期研究狀態。預設位置是 `~/.cache/alr-tw/alr_tw_storage.sqlite3`，可用 `ALR_TW_STORAGE_PATH` 改寫。

## 保存內容

- research runs 與 obligations；
- idempotent operation results；
- server-owned source records 與 evidence spans；
- TLR retrieval candidates；
- 有 TTL 的 cache metadata。

秘密值不應寫入資料庫。TLR API key 僅在請求時注入；普通裁判網站路徑不需要 API token。檔案目錄與資料庫分別設為 owner-only 權限；SQLite 啟用 foreign keys、secure delete 與 WAL。

## Retention

`ALR_TW_RETENTION` 預設為 `24h`，格式為正整數加 `s`、`m`、`h` 或 `d`，公開預覽上限 `7d`。MCP `research_legal_question.constraints.retention` 可指定相同格式，或使用 `ephemeral`：final validation 回傳後同步刪除該 run。

TTL 到期不會自動延長。背景 cleanup 與明確 purge 都必須同時處理 run、source link、evidence、candidate、operation 與不再被其他 run 引用的 source。

## CLI

```bash
alr-tw doctor
alr-tw doctor --live
alr-tw purge --run RUN_ID --confirm
alr-tw purge --all --confirm
```

可用 `--storage-path PATH` 指定另一個受管理根目錄。`--confirm` 是必要的破壞性操作確認。CLI 與 MCP 的 `purge_research_storage` 共用同一個 `PurgeService`，避免行為分歧。

`purge --all` 會關閉操作範圍內的資料庫連線後，移除主 SQLite、`-wal`、`-shm` 與 managed temp artifacts，再建立乾淨的受管理目錄。它不刪除 ALR-TW 管理範圍外的檔案。

## 限制

- 無法撤回已送到外部服務的查詢或其伺服器日誌；
- filesystem、SSD 與備份系統可能保留底層歷史區塊；
- process crash 後仍應執行 cleanup／purge audit；
- 使用者自行匯出的 trace、log 或 answer 不在 managed store 刪除範圍內。
