# Data Policy

本文件定義 ALR-TW v0.6.2 公開預覽的資料流、保存與來源信任邊界。

## 資料模式與外部傳輸

- `synthetic`：預設，完全離線；
- `official_only`：只把精確查詢送到法務部、司法院或憲法法庭官方端點；
- `hybrid_verified`：先做本地 privacy gate，再把 `safe`／`redacted_safe` 的抽象查詢送到 TLR。

不得送往 TLR 或寫入公開 issue／fixture 的資料：個人秘密、身分資訊、未公開案件完整事實、私有契約、內部代稱、訴訟策略、證據弱點與談判底線。規則無法確定時視為 `uncertain`，降級 `official_only`。

外部 provider 可能依其政策保存 access logs。ALR-TW 的本機 purge 無法刪除對方已接收的資料。啟用前應查閱外部服務當時有效的隱私與日誌政策。

## Source tiers

| Tier | 說明 | Final citation |
|---|---|---|
| `official` | 由 ALR-TW 官方 provider 取得並固定的內容 | Yes, fresh and eligible |
| `verified_cache` | 有官方 lineage、hash、verified time，或 resolver-backed JID hash match | Conditional |
| `staging` | 尚未正式驗證的匯入資料 | No |
| `external_semantic_recall` | TLR 等外部召回候選 | No |
| `synthetic` | demo／test fixture | No |
| `unknown` | 來源不明或 metadata 不足 | No |

呼叫端提交的 `official_url`、`official_hash`、`verified_at` 或 `source_tier` 不是證明。只有 server-owned provider／resolver 可以完成 evidence promotion。

## Managed storage

短期 SQLite 可保存 research run、obligation、idempotent operation result、source snapshot、evidence span、candidate 與 TTL cache metadata。預設 retention `24h`、上限 `7d`；`ephemeral` run 在 final validation 後同步清除。

不得持久化 TLR API key 或帳號密碼。普通裁判網站路徑不需要 API token。Trace 與 doctor 只回傳非敏感設定狀態，不回秘密值。

## Official change and removal

- 法規結構化內容與官方頁面衝突：標記 verification failure，不作 final evidence；
- source 到期：重新驗證前不可作 claim support；
- 司法院回覆裁判已移除／不公開：回傳 `removal_required`，managed copy 應同步移除；
- 網路失敗、官方拒絕、schema 改變與 not found 必須分開；
- 本版不保證完整歷史條文，不能把現行法冒充過去時點的法律。

## Repository boundary

不得 commit：

- 官方全文下載、裁判 SQLite／vector shards、TLR response cache；
- 真實使用者 query、answer、trace、log 或私有 eval；
- credentials、tokens、private endpoints、local sensitive paths；
- 未匿名化案件事實或受保密義務保護的內容。

Repo 只保留 source/provider contracts、public-safe code、synthetic fixtures、tests 與文件。部署者應自行確認官方授權、個資法、律師保密義務、資料保存與移除規則。

Repo 內的示範 ranking 公式與預設僅用於契約測試，不代表 production ranking 權重、embedding 或 index 設定。

## 不保證事項

ALR-TW 不保證任何來源完整、正確、即時、持續可用或適合特定個案。TLR candidate、官方即時頁面與 provider snapshot 都不能取代專業法律判斷、完整卷證及人工核對。
