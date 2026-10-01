# ALR-TW MCP agent workspace guidance

這份 agent-neutral 指引可複製到使用 ALR-TW MCP server 的 agent 工作區。它不綁定特定
IDE、模型或 agent framework；server 的工具清單與 trust gate 才是權威。

## Tool profile

- `verified` 只使用 `server_owned` 工具。
- `compatibility` 可使用 `server_owned` 與 `legacy_compatibility` 工具。
- `demo` 才暴露全部 catalog，包含 synthetic demo 工具。
- `official_only`／`hybrid_verified` 預設為 `verified`；`synthetic` 預設為
  `demo`。如需明示選擇，可設定 `ALR_TW_MCP_TOOL_PROFILE`。
- 不要假設清單中看不到的工具可直接呼叫；`tools/list` 與 `tools/call` 受同一
  profile gate，未知 profile 應在啟動時 fail closed。

## Tool selection

- 單一正式法源查證：使用 `lookup_legal_source`。
- 要引用同一 run 已驗證裁判的見解前：在有 TLR provider 的部署使用
  `inspect_judgment_lineage` 檢查 bounded 上下級審與官方主文；查無上級審
  不等於裁判確定，結果也不代表已比較前後審見解。
- 多步驟法律研究：使用 `research_legal_question`，再依
  `continue_legal_research` 的 `operation_id` 繼續。
- 結構化分析驗證：使用 `validate_legal_analysis`。
- 草稿答案驗證：使用 `validate_legal_answer`，並綁定同一 run 的 evidence。
- `agentic_legal_research`、`legal_search`、`run_agentic_demo`、
  `build_validation_report`、`exact_law_lookup`、`exact_judgment_lookup` 與
  `exact_constitutional_lookup` 是 synthetic demo 工具；不得用於真實案件、
  正式法源或正式法律引證。

這些是導流規則，不保證任意模型都能正確選擇工具。應以當前 server
profile、tool description 與回傳 envelope 為準。

## Source and citation boundary

- Synthetic fixture 只能作 demo／CI／契約測試，不能支撐真實案件答案。
- 外部 discovery（包括部署允許時的網路搜尋）可以協助找候選名稱、字號或
  locator；不要把 discovery 結果直接當成 evidence，也不必全面禁止搜尋。
- 正式引證必須回到 server-owned official verification 與 source-promotion
  gate。沒有官方驗證時，應保留 candidate／qualified 狀態並如實揭露限制。
- 立法院 connector 只在 live data mode 中由 client 明示呼叫
  `lookup_legislative_history` 時查詢；它是 optional、read-only、bounded、
  candidate-only locator。ID20、ID19、ID46、ID8、ID48 的資料不能當有效法條
  或單一立法者意旨。PDF／DOC 不解析；缺少正式公布版本時維持 `qualified`。
- 不要把 `not_found` 或 bounded scope 外的缺口寫成全球不存在，也不要用
  caller 自帶的 trust metadata 授權答案。

## Answer handling

先完成 server-owned research obligations，再用 evidence 綁定每個核心主張，
最後呼叫 `validate_legal_answer`。只有該工具回傳允許呈現的結果才可輸出；
`blocked` 或 `refusal_only` 不得帶出草稿答案。

<!-- drafting-rules:start -->
規則版本：`alr-tw.drafting-rules/v2`

- 每個實質子句（包括短結論）須由一項主張綁定完整涵蓋，不可用零碎文字拼湊覆蓋。
- 僅通過來源、精確位置與主張關聯核對的純引用標記可排除；括號內的法律結論仍須綁定驗證。
- 使用同次研究的 evidence_ids 與正式引用文字；完整綁定仍須通過支持、角色、時點及最終驗證。
- 引用位置使用原始 answer_text 的 Unicode 碼點，零起算、結尾不包含；改稿後重新定位並使用新的操作編號。
- 引用與主張放在同一子句；或完整主張後立即接單一純引導引用句（參見／參照／見／依），不得跨段、夾帶結論或有歧義。
<!-- drafting-rules:end -->

citation_text 必須是對應來源的 source.citation 正式引用名稱（裁判可用已核對的同文書等價名稱），不是 evidence.exact_text 條文或裁判原文；答案沒有引用標記時可省略 citation_occurrences，仍須完整 claim_bindings。

## Research intent clarification

快速研究只以明確用語分派來源，例如「法院如何處理……」會安排裁判召回與官方驗證。
若問題的研究意圖或詞義有歧義，先向使用者澄清，或以既有研究計畫分列待核對的解釋；
不要自行選定單一詞義，也不要為消除歧義而無限制查詢全部來源。保留原問題的否定、
角色、金額與日期。query_preparation 提供有界詞彙與日期候選，近似／相關詞不等於事實；
日期建議不自動套用，只有年月不得補日，須澄清後明示 as_of_date。不要將建議當證據或授權。
