# ALR-TW v0.6.0 Acceptance

ALR-TW v0.6.0 可宣稱為「台灣法律 Agentic RAG / MCP research safety harness 公開預覽」。它提供 server-owned research state、官方來源 providers、TLR candidate-only recall、evidence promotion、claim validation、short-lived storage 與 purge。

## 必須成立

- 預設 synthetic 離線且 fail closed；
- Live mode 必須明確選擇；
- 外部 agent 不能注入正式證據或自行決定 final status；
- TLR query 先經 privacy gate，結果不能作 final citation；
- 官方內容固定 snapshot 且有 hash、verified/expiry timestamps；
- 法規、普通裁判、憲法裁判的材料與 section roles 不混用；
- blocked 不包含 answer body；
- CLI/MCP purge 同一實作；
- 20+ v0.6 regression scenarios、legacy regressions、build 與 stdio smoke 通過；
- 公開邊界掃描無秘密、真實資料或 local-sensitive artifacts。

## 可接受的 qualified 狀態

有 fresh official evidence 支持 draft，但 TLR／普通裁判召回不可用或 counter-authority coverage 有明示限制時，可以 `qualified`。Qualification 不得掩蓋歷史法規無法確認、來源衝突、角色錯置或 claim unsupported；這些情況必須 blocked。

## 不宣稱

本版不宣稱提供 LLM、完整台灣法律資料庫、法律意見、完整歷史法規版本、普通裁判全域召回率、完整審級圖、所有附件／OCR、production SLA、零風險 privacy filter 或不可復原的資料抹除。

## Release evidence

依 [RELEASE_AUDIT_PROCEDURE.md](RELEASE_AUDIT_PROCEDURE.md) 保存：commit／worktree 狀態、ruff、mypy、pytest count、boundary scripts、wheel contents、fresh-install smoke、MCP protocol smoke、optional live checks 與外部 dependency 限制。
