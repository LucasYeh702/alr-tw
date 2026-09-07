# ALR-TW v0.12.0 Acceptance

ALR-TW v0.12.0 可宣稱為「台灣法律 Agentic RAG / MCP research safety
harness 公開預覽」。它提供 server-owned research state、agent-neutral
interoperability、官方來源 providers、TLR candidate-only recall、evidence
promotion、六種可併用法律分析分支的結構／信任驗證、claim validation、
short-lived storage 與 purge；並提供 provider-neutral applicability、
authority／judgment-lineage、公法材料 contracts 及可替換 provider SDK。

v0.12.0 同時提供 semantic verifier sidecar、provider conformance、
receipt-aware adapter 與 deployer boundary contracts。它們只驗證結構、信任、
snapshot 與公開邊界；sidecar／部署者 provider 不能建立 evidence、改變 source
trust、授權 finalization，也不會把模型、corpus、credentials 或 production
parameters 打包進公開套件。

## 必須成立

- 預設 synthetic 離線且 fail closed；
- Live mode 必須明確選擇；
- 外部 agent 不能注入正式證據或自行決定 final status；
- TLR query 先經 privacy gate，結果不能作 final citation；
- `/quick`／`快速模式：` 只可縮減研究 breadth；裁判型 query 仍須執行候選召回、
  最多五件 canonical JID／正式字號與 official text verification，以及 evidence
  sufficiency；
- `execute_legal_research` 必須保存逐步 operation audit、遇 retryable provider
  即停止，且不得代替 draft 後的 `validate_legal_answer`；
- 至少一件裁判通過官方驗證時，其他候選 mismatch／not-found／budget truncation
  最多只能形成 `qualified`／`conditional`；`0` 件通過仍須 fail closed；
- 官方內容必須由 server-owned provider 固定並具 hash、verified/expiry timestamps；
  內建 runtime 必須依同一 run 的精確合格材料集合簽發、持久化 snapshot receipt，
  並於 finalization 重算 binding；caller receipt 不可信；
- 法規、普通裁判、憲法裁判的材料與 section roles 不混用；
- 多分支 analysis 只驗證結構、scope 與 server-owned references，不宣稱
  semantic entailment 或實體涵攝正確；
- `ready_for_draft` 僅表示 workflow completion；`research_sufficiency`、
  `answer_mode` 與 server-owned finalization 才控制可回答姿態；
- finalization 只授權進入起草（`safe_to_draft`），不授權呈現答案；只有
  `validate_legal_answer` 的 `validated`／`qualified` 結果可展示；
- Coverage v2 的 bounded scope、provider scope、reason codes、snapshot receipt
  與 `absence_claim_allowed` 必須可稽核；
- counter-authority 只作最多 4 個 bounded lexical candidate queries 與最多 5 件新官方全文回查，
  沒有 semantic opposition classifier，不授權全球不存在或實務一致主張；
- applicability resolver 只依 server-owned provider metadata 解析特別法／普通法、
  上位法／下位法與新舊法時點關係；無法唯一確認時必須 fail closed，不宣稱
  自動完成語義涵攝；
- authority／judgment-lineage contract 只保存法院層級、程序姿態、上訴／審查鏈與
  bounded negative-treatment provider 結果；public-law contract／provider SDK
  只提供行政規則、行政解釋、訴願與立法資料的可替換介面，不附真實 corpus；
- synthetic fixtures 僅供 demo／契約測試，不得支撐法律答案；
- blocked 不包含 answer body；
- CLI/MCP purge 同一實作；
- `verify-provider` 只驗證有界 conformance envelope，不得把任意私有資料庫路徑
  或 caller-attested manifest 自動升格為可信 provider；
- ChronoLex-TW adapter 不內附資料集，agent input 不含 gold，歷史版本指標沒有
  evaluator-owned server adjudication 時必須是 `not_scoreable`；
- v0.12.0 contract、既有工具與 payload 的 additive compatibility、build 與 stdio smoke 應通過；
- 公開邊界掃描無秘密、真實資料或 local-sensitive artifacts。

## 可接受的 qualified 狀態

有 fresh official evidence 支持 draft，但 TLR／普通裁判召回不可用、counter-authority coverage 有明示限制，或 server snapshot receipt 缺失時，可以 `qualified`／`conditional`。內建 `ResearchService` 只有在 receipt 完整、未過期、同 run 材料 binding 與其他閘門全部通過時才能回 `ordinary`；receipt 混用或內容不符必須 fail closed。Qualification 不得掩蓋歷史法規無法確認、來源衝突、角色錯置或 claim unsupported；這些情況必須 blocked。

## 不宣稱

本版不宣稱提供 LLM、完整台灣法律資料庫、法律意見、完整歷史法規版本、普通裁判全域召回率、完整審級圖、所有附件／OCR、semantic entailment／opposition classifier、production SLA、零風險 privacy filter 或不可復原的資料抹除。

## Release evidence

依 [RELEASE_AUDIT_PROCEDURE.md](RELEASE_AUDIT_PROCEDURE.md) 保存：commit／worktree 狀態、ruff、mypy、pytest count、boundary scripts、wheel contents、fresh-install smoke、MCP protocol smoke、optional live checks 與外部 dependency 限制。
