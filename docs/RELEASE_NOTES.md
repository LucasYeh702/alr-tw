# ALR-TW v0.6.1

本版提供可安裝、可在明確模式下查詢真實官方來源的台灣法律 agentic RAG／MCP research harness，並補強 MCP host 相容性、普通裁判解析、TLR 候選升格、答案隱私與法律主張 grounding。外部 agent／LLM 負責提出問題與草擬答案；ALR-TW 則在 server 端管理研究狀態、取得來源、升格證據、驗證引用並決定答案能否呈現。

架構採台灣大陸法系角度：法規與法律時點優先，普通裁判依審級及段落角色處理，憲法法庭多數意見與個別意見分離。ALR-TW 不是法律意見服務，也不以外部檢索結果取代官方法源。

## v0.6.1 修正重點

- MCP `tools/call` 在嚴格業務參數驗證前正規化保留的 `_meta`，其他未知欄位仍拒絕
- 普通裁判 parser 支援目前的 `text-pre` 頁面、partial source 保留及 role-safe 段落分類
- TLR candidate 改以 typed identity、JID 與 provenance 回查司法院官方來源，識別不一致時阻擋 evidence promotion
- outbound query privacy 與 answer output privacy 分離，加入 deterministic redaction
- 核心法律主張以 `claim_bindings` 綁定同一 research run 的 evidence ID
- `deterministic_grounding_v2` 加入中文 n-gram、否定、例外、角色、法條與數字 anchor 檢查
- 未執行的 counter-authority search 或 keyword-only coverage 不再被標示為完整實質涵蓋
- TLR adapter 維持 clean-room 獨立實作；`mcp-taiwan-legal-db` 僅是參考對象，不是相依套件或整合元件

## 核心能力

- 新增 server-owned（伺服器持有）研究流程
  - 六個 MCP tools：`research_legal_question`、`continue_legal_research`、`get_legal_research_state`、`lookup_legal_source`、`validate_legal_answer`、`purge_research_storage`
  - 研究步驟以 ordered obligations 管理，寫入操作使用 `operation_id` 保持冪等
  - `validate_legal_answer` 只使用同一個 run 中由 server 取得並保存的證據，不接受 caller 自行宣告來源可信
- 新增真實官方來源 providers
  - 法務部中央法規：取得現行中央法規與條文資料
  - 司法院普通裁判：直接解析司法院裁判書搜尋頁與全文頁，不使用司法院 API token
  - 憲法法庭：處理判決、實體裁定、舊制解釋及可取得的個別意見
  - 官方內容通過識別、結構與一致性檢查後，才形成短期 server-owned evidence snapshot
- 接入 TLR 候選召回
  - 在 `hybrid_verified` 模式使用 [TLR（Taiwan Legal RAG）](https://github.com/aa0101181514/tw-legal-rag)尋找普通裁判候選
  - TLR 結果固定為 `external_semantic_recall`／candidate-only，不得直接作為正式引用
  - 候選必須由 ALR-TW 回查司法院官方來源，成功取得並驗證官方全文後才能升格為 evidence
  - TLR adapter 只依公開介面行為以 clean-room 方式獨立實作；`mcp-taiwan-legal-db` 不是相依套件或整合元件
- 新增三種資料模式
  - `synthetic`：安全預設，只使用合成資料，不呼叫外部服務
  - `official_only`：只查詢官方來源，不把問題送往 TLR
  - `hybrid_verified`：通過本地 privacy gate 後使用 TLR 提高候選召回，再回官方來源驗證
- 新增短期研究狀態與清除機制
  - 使用受管理的 SQLite 保存 source、candidate、evidence、obligation 與 tool event
  - 支援 TTL、最長七日 retention、`ephemeral` run 與同步 purge
  - secret 不寫入資料庫、trace、範例設定或 `doctor` 輸出
- 加強 evidence promotion 與 claim validation
  - final decision 分為 `validated`、`qualified`、`blocked`
  - 法源時點、來源 freshness、裁判段落角色與 claim support 皆納入判斷
  - blocked 結果不回傳 answer body，避免 client 顯示未通過驗證的答案
  - caller-supplied `official`、`verified_cache` 或 support metadata 不能自行取得正式證據資格
- 補強安裝、診斷與 protocol 相容性
  - 提供 `alr-tw doctor --live` 檢查 operator 設定與 live provider 狀態
  - 支援 MCP protocol `2025-11-25`、`2025-06-18`、`2025-03-26`、`2024-11-05`
  - 不支援的 protocol version 會在 initialize 階段明確拒絕

## 工程與安全文件

- 架構與可信邊界：[ARCHITECTURE_CONTRACT.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/ARCHITECTURE_CONTRACT.md)
- MCP tools 與輸入輸出契約：[TOOL_CONTRACT.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/TOOL_CONTRACT.md)
- TLR provider 與 candidate-only 規則：[TLR_PROVIDER.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/TLR_PROVIDER.md)
- 官方來源取得方式：[OFFICIAL_PROVIDERS.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/OFFICIAL_PROVIDERS.md)
- 研究資料保存與清除：[STORAGE_AND_PURGE.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/STORAGE_AND_PURGE.md)
- Trust model 與 evidence promotion：[TRUST_MODEL.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/TRUST_MODEL.md)
- Data policy 與外部查詢邊界：[DATA_POLICY.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/DATA_POLICY.md)
- Release 接受條件：[AGENTIC_HARNESS_ACCEPTANCE.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/AGENTIC_HARNESS_ACCEPTANCE.md)
- 發布審核規程：[RELEASE_AUDIT_PROCEDURE.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/docs/RELEASE_AUDIT_PROCEDURE.md)
- 完整版本變更：[CHANGELOG.md](https://github.com/LucasYeh702/alr-tw/blob/v0.6.1/CHANGELOG.md)

## 已知邊界

- 本版仍是 `0.x` public preview，MCP 介面與 schema 後續可能調整。
- 本 repo 不包含完整台灣法律資料庫、production corpus、永久官方全文快取、私有向量索引、真實使用者查詢、credential 或私有測試資料。
- 完整歷史法規版本、普通裁判全域召回率、完整審級關係及所有附件／程序裁定仍未承諾。
- TLR 是外部候選召回服務，其可用性、完整性、排序與更新速度不由 ALR-TW 保證；正式引用仍須回到官方來源驗證。
- 啟用 `hybrid_verified` 時，通過 privacy gate 的查詢會送往 TLR；不得輸入個人秘密、未公開案情、私有契約、訴訟策略、證據弱點或談判底線。
- 本專案不是律師服務或法律意見，所有輸出仍應由具資格人員依官方原文、法律時點與具體事實複核。

## 發布前檢核（Pre-push checklist）

- `python3 scripts/check_no_forbidden_files.py`
- `python3 scripts/check_public_boundary.py`
- `uv run --extra dev ruff check .`
- `uv run --extra dev mypy src`
- `uv run --extra dev pytest -q`
- `uv build`

## 版本建議

- release tag：`v0.6.1`
- release title：`v0.6.1`
