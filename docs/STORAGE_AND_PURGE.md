# Storage and Purge

> 適用版本：v1.0.0（套件 `1.0.0`）；功能與限制見 [1.0 說明](V1_RELEASE.md)。


ALR-TW v1.0.0 使用單一 managed SQLite store（受管理 SQLite 儲存）保存短期研究狀態。預設位置是 `~/.cache/alr-tw/alr_tw_storage.sqlite3`，可用 `ALR_TW_STORAGE_PATH` 改寫。

## 保存內容

- research runs 與 obligations；
- idempotent operation results；
- server-owned source records 與 evidence spans；
- TLR retrieval candidates；
- Coverage v2、research sufficiency、answer mode 與 server-owned finalization 摘要；
- 內建 `ResearchService` 依同一 run 精確合格材料集合簽發、持久化的
  provider-neutral snapshot receipts；finalization 會從 store 讀取並重算 binding；
- receipt 缺失時最高為 `conditional`，跨 run、過期或集合不一致時 fail closed；
  只有 receipt 與其他閘門均通過時 `ordinary` 才可達；
- 有 TTL 的 cache metadata。

秘密值不應寫入資料庫。TLR API key 僅在請求時注入；普通裁判網站路徑不需要 API token。檔案目錄與資料庫分別設為 owner-only 權限；SQLite 啟用 foreign keys、secure delete 與 WAL。

## Retention

`ALR_TW_RETENTION` 預設為 `24h`，格式為正整數加 `s`、`m`、`h` 或 `d`，上限 `7d`。MCP `research_legal_question.constraints.retention` 可指定相同格式，或使用 `ephemeral`：final validation 回傳後同步刪除該 run。

TTL 到期會使研究／證據失去使用資格，不會自動延長，也不等於磁碟內容已刪除。
本版提供 `cleanup_expired` 儲存方法，但不內建背景排程器；部署者須安排清理，或透過 CLI／MCP 明確 purge。
清理涵蓋研究及其來源關聯、證據、候選、操作、快照回執與不再被其他研究引用的來源；
外部備份與檔案系統快照不在受管清除範圍。

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


本版的本機受管操作以程序鎖互斥；程序終止後可用新操作編號接續，舊操作不改為成功。舊版無鎖紀錄不自動接管，亦不得混跑舊／新版 writer。詳細範圍見 [1.0 操作與限制](V1_RELEASE.md)。
