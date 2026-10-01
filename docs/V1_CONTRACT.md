# 1.0 公開契約

適用套件 `1.0.0`。以下 1.x 穩定承諾自 1.0.0 生效。
本版保留工具輸入與信任邊界，新增研究預算輸出及部署預設；升級影響與回歸見 V1_UPGRADE。
版本身分使用 `_version.__version__` 供套件及 MCP 讀取，建置設定以一致性測試核對。
協定、資料包、起草規則及資料結構版本不隨套件版本改名。

## 支援層級

- **穩定核心**：研究建立／接續／計畫、來源精確查證、研究狀態、起草姿態、草稿預檢、答案驗證及清除。
- **穩定可選**：TLR 候選提供者介面、有界歷審檢查、結構化法律分析驗證、HMAC 本機資料包與提供者相容介面。關閉不妨礙核心；啟用遵循同一信任規則。
- **有限支援**：立法 locator、有限歷史法規／函釋、小型遠端精確包、語意顧問。依原有明列範圍使用，不承諾全域資料覆蓋。有限覆蓋不降低信任檢查。
- **內部／舊相容**：legacy／synthetic 工具、Python 私有函式、SQLite 內部表結構與評測端腳本。保留現行 profile gate；不列為 1.x 穩定介面。

## MCP 介面

每項欄位型別、上下限與巢狀結構由既有工具目錄及 Pydantic 型別產生；
`tools/list` 是可執行結構規格，`TOOL_CONTRACT.md` 說明具體語義。
以下將穩定層級、必要／可選輸入與效果綁定在同一份契約文件，不另建註冊服務。

| 工具 | 層級 | 必要輸入 | 可選輸入 | 輸出／信任效果 | 網路／保存 |
|---|---|---|---|---|---|
| `review_legal_draft` | 核心 | `run_id`, `answer_text`, `claim_bindings` | 無 | 探索草稿、標註及位置提案；永不授權 | 無／唯讀 |
| `complete_legal_research` | 核心 | `run_id`, `answer_text`, `claim_bindings`, `operation_id` | `max_steps` | 接續及嚴格驗證；非原子交易 | 依未完成義務／操作 |
| `get_legal_research_capabilities` | 核心 | 無 | 無 | 能力與固定指引；不授權 | 無／無 |
| `research_legal_question` | 核心 | `query` | `client_id`, `constraints`, `request_id` | 研究與義務；不授權 | 依模式／建立 run |
| `execute_legal_research` | 核心 | `query` | `constraints`, `max_steps`, `operation_prefix` | 有界步驟、狀態及證據；不授權答案 | 依提供者／run 與操作 |
| `submit_legal_research_plan` | 核心 | `run_id`, `operation_id`, `plan` | `request_id` | 未信任提案；不能自行建立證據 | 無／提案與摘要 |
| `continue_legal_research` | 核心 | `run_id`, `operation_id` | `request_id` | 下一義務與錯誤；相同操作摘要才能重播 | 依提供者／操作 |
| `get_legal_research_state` | 核心 | `run_id` | 無 | 進度、限制及短指引；不是答案核准 | 無／唯讀 |
| `get_legal_research_finalization` | 核心 | `run_id` | 無 | 伺服器起草姿態；不是最終答案核准 | 無／既有狀態投影 |
| `lookup_legal_source` | 核心 | `text` | `operation_id`, `run_id` | 正式來源與證據；來源命中不等於主張成立 | 官方或可信包／依既有工具流程保存 |
| `inspect_judgment_lineage` | 穩定可選 | `run_id`, `jid`, `operation_id` | `max_related_nodes` | 有界歷審與來源核對；不證明確定性 | 候選及官方／操作 |
| `lookup_legislative_history` | 有限 | `as_of_date`, `bounded_scope` | `bill_no`, `law_identifier`, `law_name`, `max_results`, `session`, `term` | locator 候選；不是正文或有效法條 | 官方／有界結果 |
| `validate_legal_analysis` | 穩定可選 | `run_id`, `operation_id`, `analysis` | `request_id` | 結構驗證；不授權答案或一般法律涵攝 | 無／操作 |
| `validate_legal_answer` | 核心 | `run_id`, `answer_text`, `operation_id` | `claim_bindings`, `request_id` | 嚴格決策、受控答案與限制 | 無／操作及決策 |
| `purge_research_storage` | 核心 | `scope`, `confirm` | `run_id` | 受管儲存清除；不涵蓋外部副本 | 無／清除 |

`lookup_legislative_history` 另要求 `law_name` 或 `law_identifier` 至少一項。
`validate_legal_answer` 的綁定欄位保留為輸入結構上的可選，以保留舊 caller 的明確受限回應；
核心主張缺綁定不能取得正式放行。不得解讀為不用提供證據。

## 輸出、錯誤與展示

沿用既有 schema 與 `TOOL_CONTRACT.md`：研究 run／state、step-result、execution、
finalization、draft-workspace、answer-validation/v4 各自管理版本。
`workflow_complete`、`ready_for_draft`、`answer_mode`、`safe_to_present` 不可互代。

- 最終 `validated`／`qualified` 且 `safe_to_present=true` 才能使用回傳的正式答案；
  `qualified` 的限制必須完整呈現。這些狀態不證明一般法律推理正確。
- `blocked`／`refusal_only` 不回傳可展示的未授權草稿。唯讀內部草稿另有明確標示，永不授權。
- 位置提案只對原草稿摘要有效；改稿須重新預檢、用新操作編號完整驗證。
- `OPERATION_REQUEST_MISMATCH`、`OPERATION_RESULT_STALE`、`RESEARCH_RUN_EXPIRED`、
  `OPERATION_IN_PROGRESS` 及 `STORAGE_PATH_CHANGED` 都不是成功；錯誤後不得展示舊答案。
- 網路錯誤、查無、範圍缺漏、截斷與逾時各自回報；不能推論全域不存在、實務一致或裁判確定。
- JSON-RPC 未初始化、參數不合、不支援協定及內部例外沿用既有錯誤包裝；
  caller 不能以額外的 trust／safe_to_present 欄位變更伺服器裁決。

輸出解析器需依協定允許的擴充位置處理未知欄位；不能預設新增列舉或預設值一定相容。
1.x 新增／棄用先驗證舊客戶端；穩定公開面不相容移除／改動需新主版。
安全缺陷不保留錯誤放行，但要說明受影響行為；不得用安全名義隱藏真正契約破壞。

## CLI、設定與提供者

CLI 保留 `quick-research`、`research-status`、`review-draft`、`validate-draft`、
`complete-research`、`purge`、`doctor`。成功／受限與錯誤以既有 JSON 包裝與退出碼為準，
驗收使用實際安裝命令而非僅呼叫函式。完整參數見 `--help` 與研究工作流程文件。

`build-pack`／`inspect-pack`／`import-pack` 是穩定可選；資料包仍為
`alr-tw.judgment-pack/v1`，需外部可信金鑰、hash、期限及 schema 核對；不是司法簽章。
`map-quote` 是唯讀輔助；歷史法規、函釋、遠端資料包及顧問維持原明示啟用與有限範圍。
評測與示範工具不加入穩定核心，Gemini 接入不重啟。

設定沿用 `.env.example` 的名稱、預設與啟用方式；新安裝應明示資料模式，未知模式拒絕。
`synthetic` 預設 demo profile，`official_only`／`hybrid_verified` 預設 verified；
選擇 profile 不會自行授權證據。秘密不回傳、不寫入測試或版本庫。
提供者依 `PROVIDER_ACCEPTANCE.md` 既有注入介面與故障矩陣；外部提供者不能自簽正式答案權限。

## 支援矩陣與驗收定位

| 面向 | 支援範圍 | 驗收與限制 |
|---|---|---|
| 執行環境 | 單使用者、單受管信任域、POSIX 本機 stdio | 不宣稱 Windows、多租戶、跨主機或 SLA |
| macOS | Python 3.12 base、Python 3.11 TLR-only | 本機隔離 wheel 與跨程序 smoke；不代表所有 macOS 組合 |
| Linux | Python 3.12 base／TLR-only、Python 3.11 TLR-only | CI 實際產物安裝；最低 Python 3.11 |
| MCP 協定 | 2025-11-25、2025-06-18、2025-03-26、2024-11-05 | 初始化／發現／能力呼叫／錯誤回歸；不是所有客戶端工作流驗證 |
| 升級 | 公開 0.12.0 | 真實舊套件寫入 → 1.0.0 套件讀取；見升級指南 |

相容測試：`test_v1_candidate_contract.py` 固定入口與初始化行為；
`scripts/smoke_upgrade.py` 使用隔離舊／新套件核對輸入、設定、研究、重播、期限及清除；
與 0.14 回歸保留，`smoke_installed_workflows.py` 驗證 W1–W3 的實際命令與跨程序接續。
不建立新的契約管理或評測平台。

## 預算界線

既有 max_steps、裁判查證數、回應上限與個別提供者 timeout 保留。
本版為每個研究保存 `budget`：期限、累計 HTTP 嘗試、上限與耗盡原因。
`ALR_TW_RESEARCH_MAX_SECONDS` 預設 120（大於 0、至多 3600）；
`ALR_TW_RESEARCH_MAX_HTTP_REQUESTS` 預設 50（1–1000）。設定只作用於新研究。
舊記錄首次使用以預設預算讀取，不接受客戶端注入或重設預算。

首次推進或綁定研究的查證／歷審查詢啟動期限，包含呼叫間等待，跨程序保存；
同操作重播不再次收費。官方、TLR 與遠端資料包的內建非同步 HTTP 傳輸，在送出前
計次，包含重新導向、失敗嘗試與重試；快取命中不算 HTTP。提供者協程受剩餘時間取消，
逾時與用盡請求數停止新工作，回報 `TIMEOUT_BUDGET_EXHAUSTED` 或
`HTTP_BUDGET_EXHAUSTED`；批次推進的 `stop_reason=budget_exhausted`。
不將未完成義務標成已完成，不刪除已保存材料、不延長來源期限、不授權最終答案。

這是受管研究的 I/O 與推進期限，不是對任意同步擴充程式、CPU 密集解析、
作業系統排程或磁碟停頓的硬即時保證。取消後必要清理可能增加返回耗時。
未綁定研究的獨立查證、可選立法定位與外部客戶端呼叫不包含在每研究預算內，
仍受各自原有上限。自訂提供者必須採受管傳輸才能取得完整 HTTP 計數。
外部模型的 token 消耗不可觀測，`used_total_tokens=null`，不代表零費用；
客戶端須自行限制模型預算。本版沒有伺服器模型呼叫或新增 Gemini 接入。

引用位置的 citation_text 使用來源正式引用名稱，不使用證據原文。
缺少研究的 MCP 錯誤為 RESEARCH_RUN_NOT_FOUND（JSON-RPC -32602），直接服務方法
以 ValueError 回報；非預期內部錯誤仍隱藏細節。唯讀狀態可供診斷，不能單憑 planning
推定研究尚未到期；到期研究的推進／最終驗證會拒絕。

裁判同文書等價與單一相鄰純引導句的接受範圍見 V1_RELEASE。
起草指引升為 v2；來源、角色、支持與重播規則保持嚴格，不支援任意名稱或跨句推斷。

批次位置提案仍唯讀且不授權；限定詞關係不明回傳待審，可能比舊版更嚴格。
分院完整名稱參與同文書比對；新增明確法院實務問句的有界分派。詳見 V1_RELEASE。

研究建立／狀態回應包含可選 query_preparation 區塊，不新增 MCP 工具或必要輸入。
原問題經既有命令解析後保留；查詢上限 16,384 碼點／65,536 UTF-8 位元組，空字串、
無效 Unicode 與不允許的控制字元以不含原文的 RESEARCH_QUERY_INVALID 拒絕。
日期及搜尋候選只供澄清與檢索；不改寫 as_of_date、不改來源資格或正式答案驗證。

提供可選 query_preparation.law_search_queries，以獨立詞候選適配官方法規
連續字串搜尋，保留 surface／relation／weight 及 original_query。search_queries
仍供官方裁判使用，外部服務只接收原問題。期間及一般制度詞不再強加歷史法義務；
明示歷史需求與真正日期仍保持時點查證。MCP 工具數與儲存結構不變。
