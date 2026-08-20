# ALR-TW v0.10.0 版本說明

## 主要變更

- MCP tool surface 改由單一 catalog 管理，並新增 `verified`、
  `compatibility`、`demo` profiles。`official_only`／`hybrid_verified` 預設
  `verified`，只暴露 server-owned tools；`synthetic` 預設 `demo`。
- `tools/list` 與 `tools/call` 使用同一個 session-fixed profile。若 client
  快取後呼叫目前 profile 不允許的工具，會得到穩定的
  `TOOL_NOT_AVAILABLE_IN_PROFILE`，而不是執行被隱藏的實作。
- `get_legal_research_capabilities` 現會回報 active profile 與可用工具名稱，
  供 Agent 在呼叫前選路。
- 新增 server-owned `lookup_legislative_history` 與 optional 立法院開放資料
  connector，提供有界限、唯讀、candidate-only 的議案與立法程序 locator。

## 升級注意

live mode 的預設 `tools/list` 由 24 個工具縮減為 server-owned tools，這是
刻意的 Agent 體驗與安全收斂。仍需舊版 helper 的 client 可設定：

```text
ALR_TW_MCP_TOOL_PROFILE=compatibility
```

只有 CI、教學或 synthetic harness 才應使用：

```text
ALR_TW_MCP_TOOL_PROFILE=demo
```

未知 profile 會在 session 啟動時 fail closed。

## 立法院 connector 的可宣稱範圍

- 使用立法院官方資料集定位議案提案、法律條文對照表、委員會議案、
  黨團協商及三讀議案。
- 資料列與官方 PDF／DOC 連結仍是 candidate；本版不下載或解析 linked
  documents，也不把議案、審查或三讀資料當成現行有效法條。
- 官方 `data.ly.gov.tw` 目前缺少 secure-renegotiation 支援；OpenSSL 3 client
  僅對此固定 origin 允許初始 legacy-server-connect，相同 context 仍執行
  CA／hostname 驗證並禁止後續 renegotiation。若 runtime 無此相容能力，查詢
  fail closed，不改走非官方或明文來源。
- 缺少可驗證文件日期、唯一議案關聯或正式公布版本時，結果必須維持
  partial／qualified。`not_found_in_scope` 不能擴張成「沒有立法理由」。

## 保留的安全邊界

- v0.9.1 對 caller-attested citations 的修補繼續有效；caller 自稱
  `official`、提供 URL／hash／verified time 或偽造 resolver 狀態，仍不能
  取得最終引用或答案呈現資格。
- `ResearchService.validate_legal_answer` 的 server-owned evidence、claim
  binding 與 finalization gates 不受 tool profile 或立法 locator 影響。
- 本版仍是 public preview，不提供完整台灣法律資料庫、語義蘊含判斷或
  production SLA。
